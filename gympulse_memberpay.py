"""GymPulse AI · members pay their gym online, and can renew automatically by card.

How the money moves
* Each gym gets a Paystack *subaccount* under GymPulse AI's Paystack account, with the gym's own bank account
  (Grow -> Collect renewals -> Online payments). GymPulse takes 0%; Paystack pays the gym's bank directly and the
  gym bears Paystack's fee (bearer = subaccount).
* A member's personal link (usegympulseai.com/?pay=<member>.<signature>) shows their plan and price and sends them
  to Paystack. When Paystack confirms, the renewal is recorded in GymPulse automatically (payments, new end date,
  credit to the play that earned it). The Paystack sync job also records payments where the member closed the page.
* Paying by card, a member can tick "renew automatically". Paystack returns a reusable *authorization* (a token, not
  the card number). On the renewal date the daily job charges it once; if that fails, the normal reminders go out.
  Members stop it from their pay link at any time.

Stored in platform_settings (gyms can't read these keys):
  "gym_paystack": {"gyms": {gym_id: {"subaccount", "bank", "bank_code", "account_last4", "account_name", "since"}}}
  "member_cards": {"gyms": {gym_id: {member_id: {"auth", "email", "last4", "brand", "exp", "on", "since"}}}}
Each Paystack payment is applied once (billing_events ref "member:<reference>").
"""
import hashlib
import hmac
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote as url_quote

import streamlit as st

import gympulse_workspaces as gw

PAY_PARAM, DONE_PARAM = "pay", "pay_done"
SUB_KEY, CARDS_KEY = "gym_paystack", "member_cards"
AUTO_CHARGE_GRACE = 3            # also try a saved card up to 3 days after the plan ended


# ------------------------------------------------------------------ plumbing
def _service():
    import gympulse_billing as gbill
    return gbill._service()


def _paystack(method, path, **kw):
    import gympulse_billing as gbill
    return gbill._paystack(method, path, **kw)


def _secret():
    import gympulse_admin as gadm
    return (gadm._env("SUPABASE_SERVICE_ROLE_KEY") or "gympulse").encode()


def _sign(member_id):
    return hmac.new(_secret(), str(member_id).encode(), hashlib.sha256).hexdigest()[:20]


def pay_url(member_id):
    return f"{gw.APP_URL}/?{PAY_PARAM}={member_id}.{_sign(member_id)}"


def parse_token(token):
    mid, _, sig = str(token or "").partition(".")
    return mid if mid and sig and hmac.compare_digest(sig, _sign(mid)) else None


_MEMO = {}            # key -> (time, gyms): one read serves a whole page, not one per member card
_MEMO_TTL = 30


def _load(sc, key):
    hit = _MEMO.get(key)
    if hit and time.time() - hit[0] < _MEMO_TTL:
        return dict(hit[1])
    try:
        rows = sc.table("platform_settings").select("value").eq("key", key).limit(1).execute().data
        gyms = dict((rows[0]["value"] or {}).get("gyms") or {}) if rows else {}
    except Exception:
        return {}
    _MEMO[key] = (time.time(), gyms)
    return dict(gyms)


def _save(sc, key, gyms):
    _MEMO.pop(key, None)
    sc.table("platform_settings").upsert({"key": key, "value": {"gyms": gyms},
                                          "updated_at": datetime.now(timezone.utc).isoformat()},
                                         on_conflict="key").execute()


def gym_account(sc, gym_id):
    return _load(sc, SUB_KEY).get(str(gym_id)) if sc and gym_id else None


def with_member_link(pay, gym_id, member_id, sc=None):
    """The gym's payment details plus this member's own pay link, when the gym takes payments online."""
    pay = dict(pay or {})
    try:
        if member_id and gym_account(sc or _service(), gym_id):
            pay["member_pay_url"] = pay_url(member_id)
    except Exception:
        pass
    return pay


# ------------------------------------------------------------------ the gym connects its bank account
@st.cache_data(ttl=86400, show_spinner=False)
def banks():
    r = _paystack("GET", "/bank", params={"country": "nigeria", "perPage": 200})
    return sorted([(b["name"], b["code"]) for b in r.get("data") or [] if b.get("active", True) and b.get("code")],
                  key=lambda x: x[0].lower())


def resolve(account, bank_code):
    r = _paystack("GET", "/bank/resolve", params={"account_number": account, "bank_code": bank_code})
    return (r.get("data") or {}).get("account_name") if r.get("status") else None


def connect(sc, gym_id, business_name, bank_name, bank_code, account, account_name):
    """Create (or update) the gym's Paystack subaccount. Returns (ok, message)."""
    current = gym_account(sc, gym_id)
    body = {"business_name": business_name[:100], "settlement_bank": bank_code, "account_number": account,
            "percentage_charge": 0, "description": f"GymPulse AI gym {gym_id}"}
    if current and current.get("subaccount"):
        r = _paystack("PUT", f"/subaccount/{current['subaccount']}", json=body)
    else:
        r = _paystack("POST", "/subaccount", json=body)
    if not r.get("status"):
        return False, r.get("message") or "Paystack didn't accept those details."
    code = (r.get("data") or {}).get("subaccount_code") or (current or {}).get("subaccount")
    gyms = _load(sc, SUB_KEY)
    gyms[str(gym_id)] = {"subaccount": code, "bank": bank_name, "bank_code": bank_code,
                         "account_last4": account[-4:], "account_name": account_name,
                         "since": (current or {}).get("since") or gw.today_local().isoformat()}
    _save(sc, SUB_KEY, gyms)
    return True, f"Online payments are on. Members' payments go to {account_name} ({bank_name}, ending {account[-4:]})."


def disconnect(sc, gym_id):
    gyms = _load(sc, SUB_KEY)
    gyms.pop(str(gym_id), None)
    _save(sc, SUB_KEY, gyms)


def render_setup(supabase, gym_id, business_name):
    """Grow -> Collect renewals: switch on online payments (card, transfer, USSD) through GymPulse."""
    sc = _service()
    import gympulse_billing as gbill
    if not (sc and gbill.paystack_key()):
        return
    acc = gym_account(sc, gym_id)
    with st.expander("Online payments: card, transfer or USSD" + (" · on" if acc else ""),
                     icon=":material/credit_card:", expanded=False):
        st.caption("Members pay from their renewal message, and GymPulse renews them by itself: no receipts to "
                   "check. Payments are processed by Paystack and paid straight into your bank account. GymPulse "
                   "takes nothing; Paystack's standard fee is taken from each payment. Members paying by card can "
                   "choose to renew automatically.")
        if acc:
            st.success(f"On. Payments go to {acc.get('account_name')} ({acc.get('bank')}, ending "
                       f"{acc.get('account_last4')}).", icon=":material/check_circle:")
        try:
            options = banks()
        except Exception:
            options = []
        if not options:
            st.info("Paystack's bank list isn't available right now. Please try again in a minute.")
            return
        names = [n for n, _ in options]
        codes = dict(options)
        c1, c2 = st.columns(2)
        bank = c1.selectbox("Bank", names, index=names.index(acc["bank"]) if acc and acc.get("bank") in names else None,
                            placeholder="Choose your bank", key="mp_bank")
        account = c2.text_input("Account number", max_chars=10, placeholder="10 digits", key="mp_acct")
        go = st.button("Check account and switch on" if not acc else "Change account", type="primary", key="mp_go")
        if go:
            digits = "".join(ch for ch in account if ch.isdigit())
            if not bank or len(digits) != 10:
                st.error("Choose your bank and enter the 10-digit account number.")
                return
            name = resolve(digits, codes[bank])
            if not name:
                st.error("Paystack couldn't find that account. Check the bank and the number.")
                return
            st.session_state["mp_pending"] = (bank, codes[bank], digits, name)
        pend = st.session_state.get("mp_pending")
        if pend:
            st.info(f"Paystack says this account belongs to **{pend[3]}**. Is that your business account?")
            a, b = st.columns(2)
            if a.button("Yes, use this account", type="primary", key="mp_yes", use_container_width=True):
                ok, msg = connect(sc, gym_id, business_name, *pend)
                st.session_state.pop("mp_pending", None)
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()
            if b.button("No, change it", key="mp_no", use_container_width=True):
                st.session_state.pop("mp_pending", None)
                st.rerun()
        if acc and st.button("Switch online payments off", type="tertiary", key="mp_off"):
            disconnect(sc, gym_id)
            st.rerun()


# ------------------------------------------------------------------ a member pays
def _member(sc, member_id):
    rows = sc.table("members").select("id, gym_id, full_name, email, membership_end, archived") \
        .eq("id", member_id).limit(1).execute().data or []
    if not rows:
        return None, None
    m = rows[0]
    act = sc.table("member_activity").select("membership_type, monthly_fee").eq("member_id", member_id) \
        .limit(1).execute().data or []
    m.update(act[0] if act else {})
    plan = gw.plan_name(m.get("membership_type"))
    amount = round(float(m.get("monthly_fee") or 0) * gw.PLAN_MONTHS[plan], 2)
    try:                                                   # a "discount to stay" the member accepted
        import gympulse_saveoffer as gso
        offer = gso.pending(sc, member_id)
    except Exception:
        offer = None
    if offer and amount > 0:
        m["_offer"] = offer
        amount = round(max(0.0, amount - float(offer.get("discount") or 0)), 2)
    return m, (plan, amount)


def _gym_name(sc, gym_id):
    rows = sc.table("gyms").select("business_name").eq("id", gym_id).limit(1).execute().data or []
    return gw._text(rows[0].get("business_name") if rows else "", "your gym")


def _cards(sc, gym_id):
    return _load(sc, CARDS_KEY).get(str(gym_id)) or {}


def _set_card(sc, gym_id, member_id, card):
    gyms = _load(sc, CARDS_KEY)
    gym = dict(gyms.get(str(gym_id)) or {})
    if card is None:
        gym.pop(str(member_id), None)
    else:
        gym[str(member_id)] = card
    gyms[str(gym_id)] = gym
    _save(sc, CARDS_KEY, gyms)


def _email_for(m, typed=""):
    e = gw._text(typed or m.get("email")).strip()
    return e if "@" in e and "." in e.split("@")[-1] else f"m{str(m['id']).replace('-', '')[:12]}@members.usegympulseai.com"


def start(sc, m, plan, amount, email, auto_renew):
    """Open a Paystack payment for this member's renewal. Returns (url or None, message)."""
    acc = gym_account(sc, m["gym_id"])
    if not acc:
        return None, "This gym doesn't take online payments yet. Please pay at the front desk."
    ref = f"gm-{str(m['id'])[:8]}-{uuid.uuid4().hex[:12]}"
    r = _paystack("POST", "/transaction/initialize", json={
        "email": email, "amount": int(round(amount * 100)), "currency": "NGN", "reference": ref,
        "subaccount": acc["subaccount"], "bearer": "subaccount",
        "callback_url": f"{gw.APP_URL}/?{DONE_PARAM}=1",
        "metadata": {"source": "gympulse_member", "gym_id": m["gym_id"], "member_id": m["id"], "plan": plan,
                     "auto_renew": bool(auto_renew), "email": email}})
    if not r.get("status"):
        return None, "We couldn't open the payment page. Please try again in a minute."
    return (r.get("data") or {}).get("authorization_url"), ""


def apply(reference, sc=None):
    """Check a member payment with Paystack and renew the member. Safe to call many times.
    Returns (ok, message, details dict)."""
    import gympulse_revenue as grev
    sc = sc or _service()
    r = _paystack("GET", f"/transaction/verify/{url_quote(str(reference), safe='')}")
    d = r.get("data") or {}
    if not r.get("status") or d.get("status") != "success":
        return False, "That payment hasn't gone through yet. If money left your account, it will show shortly.", {}
    md = d.get("metadata") or {}
    if md.get("source") != "gympulse_member" or not md.get("member_id"):
        return False, "That payment isn't for a gym membership.", {}
    m, (plan, expected) = _member(sc, md["member_id"])
    if not m:
        return False, "We couldn't find that membership. The gym will confirm your payment.", {}
    paid = (d.get("amount") or 0) / 100
    try:
        end_now = date.fromisoformat(str(m.get("membership_end"))[:10]) if m.get("membership_end") else None
    except ValueError:
        end_now = None
    info = {"gym": _gym_name(sc, m["gym_id"]), "first": (gw._text(m.get("full_name")).split() or ["there"])[0]}
    try:
        sc.table("billing_events").insert({"gym_id": m["gym_id"], "kind": "paystack",
                                           "ref": f"member:{reference}"}).execute()
    except Exception:
        info["until"] = end_now
        return True, "Payment received. Your membership is renewed.", info          # already applied
    if paid + 0.5 < expected:
        import gympulse_billing as gbill
        gbill._email_founder(f"Member payment to check: {reference}",
                             f"A member paid NGN {paid:,.0f} for a {plan} plan that costs NGN {expected:,.0f} "
                             f"(gym {m['gym_id']}, member {m['id']}). Not applied automatically.")
        return False, "We've received your payment and the gym will confirm it shortly.", info
    today = gw.today_local()
    start_day = end_now if end_now and end_now >= today else today
    grev.record_payment(sc, m["gym_id"], m["id"], m.get("full_name") or "Member", paid, plan, start_day,
                        method="Paystack (online)", current_end=end_now, act=True,
                        note=f"Paid online, Paystack {reference}"
                             + (f" ({int(m['_offer']['percent'])}% discount to stay)" if m.get("_offer") else ""))
    if m.get("_offer"):
        try:
            import gympulse_saveoffer as gso
            gso.mark_used(sc, m["_offer"]["id"], reference)    # the discount is used once
        except Exception:
            pass
    info["until"] = start_day + timedelta(days=gw.PLAN_DAYS[plan])
    auth = d.get("authorization") or {}
    if md.get("auto_renew") and auth.get("reusable") and auth.get("authorization_code"):
        _set_card(sc, m["gym_id"], m["id"], {"auth": auth["authorization_code"], "email": md.get("email") or
                                             (d.get("customer") or {}).get("email"), "last4": auth.get("last4"),
                                             "brand": gw._text(auth.get("card_type")).strip().title(),
                                             "exp": f"{auth.get('exp_month')}/{auth.get('exp_year')}", "on": True,
                                             "since": today.isoformat()})
        info["auto"] = True
    return True, f"Payment received. Your membership is active until {info['until']:%d %B %Y}.", info


# ------------------------------------------------------------------ automatic card renewals (daily job)
def charge_due(sc, dry_run=False, log=print, today=None):
    """Charge saved cards for memberships ending today (or up to 3 days ago). One try per renewal date.
    Returns (charged, failed)."""
    today = today or gw.today_local()
    accounts = _load(sc, SUB_KEY)
    charged = failed = 0
    for gym_id, cards in _load(sc, CARDS_KEY).items():
        acc = accounts.get(gym_id)
        if not acc:
            continue
        for member_id, card in (cards or {}).items():
            if not card.get("on") or not card.get("auth"):
                continue
            try:
                m, (plan, amount) = _member(sc, member_id)
            except Exception:
                continue
            if not m or m.get("archived") or amount <= 0 or not m.get("membership_end"):
                continue
            end = date.fromisoformat(str(m["membership_end"])[:10])
            if not (0 <= (today - end).days <= AUTO_CHARGE_GRACE):
                continue
            key = f"auto:{member_id}:{end.isoformat()}"
            try:
                tried = sc.table("billing_events").select("ref").eq("ref", key).limit(1).execute().data
            except Exception:
                tried = []
            if tried:
                continue
            log(f"  {m.get('full_name')}: NGN {amount:,.0f} by saved card" + (" (dry run)" if dry_run else ""))
            if dry_run:
                continue
            sc.table("billing_events").insert({"gym_id": gym_id, "kind": "paystack", "ref": key}).execute()
            ref = f"ga-{str(member_id)[:8]}-{uuid.uuid4().hex[:12]}"
            r = _paystack("POST", "/transaction/charge_authorization", json={
                "email": card.get("email") or _email_for(m), "amount": int(round(amount * 100)),
                "authorization_code": card["auth"], "reference": ref, "subaccount": acc["subaccount"],
                "bearer": "subaccount",
                "metadata": {"source": "gympulse_member", "gym_id": gym_id, "member_id": member_id, "plan": plan,
                             "auto_renew": True, "email": card.get("email")}})
            if r.get("status") and (r.get("data") or {}).get("status") == "success":
                ok, msg, _ = apply(ref, sc)
                charged += ok
                log(f"    {msg}")
            else:
                failed += 1
                log(f"    card charge didn't go through: {(r.get('data') or {}).get('gateway_response') or r.get('message')}")
    return charged, failed


# ------------------------------------------------------------------ public pages
def render_pay(token):
    """usegympulseai.com/?pay=<token>: a member's renewal, paid online."""
    import gympulse_booking as gb
    gb._header()
    col = gw.center("memberpay", 560)
    with col:
        sc = _service()
        mid = parse_token(token)
        m, price = _member(sc, mid) if (sc and mid) else (None, None)
        if not m or m.get("archived"):
            st.error("This payment link isn't valid. Please ask your gym for a new one.")
            return
        plan, amount = price
        gym = _gym_name(sc, m["gym_id"])
        first = (gw._text(m.get("full_name")).split() or ["there"])[0]
        acc = gym_account(sc, m["gym_id"])
        gw._md(f'<div class="bk-title">Renew at {gw._esc(gym)}</div>'
               f'<div class="bk-sub">Hi {gw._esc(first)}. Your {gw.plan_phrase(plan)} membership'
               + (f" ends on {date.fromisoformat(str(m['membership_end'])[:10]):%A %d %B}" if m.get("membership_end")
                  else "") + ".</div>")
        if not acc or amount <= 0:
            st.info("Online payment isn't set up for this gym yet. Please renew at the front desk.")
            return
        card = _cards(sc, m["gym_id"]).get(str(m["id"]))
        if card and card.get("on"):
            st.success(f"Automatic renewal is on with your {card.get('brand') or 'card'} ending {card.get('last4')}. "
                       "We'll charge it on your renewal date.", icon=":material/autorenew:")
            if st.button("Stop automatic renewal", key="mp_stop"):
                _set_card(sc, m["gym_id"], m["id"], {**card, "on": False})
                st.success("Automatic renewal is off. Nothing will be charged.")
                return
        gw._md(f'<div style="font-size:30px;font-weight:700;margin:10px 0 4px">₦{amount:,.0f}</div>'
               f'<div class="bk-small">{gw.plan_phrase(plan).capitalize()} plan · paid to {gw._esc(gym)}</div>')
        if m.get("_offer"):
            st.caption(f"Includes your {int(m['_offer']['percent'])}% discount for staying "
                       f"(₦{float(m['_offer']['discount']):,.0f} off).")
        with st.form("mp_form", border=False):
            email = st.text_input("Email for your receipt", value=gw._text(m.get("email")),
                                  placeholder="you@example.com")
            auto = st.checkbox("Renew automatically with this card each time (you can stop it any time)",
                               help="Only for card payments. Your card details stay with Paystack; GymPulse never "
                                    "sees them.")
            go = st.form_submit_button(f"Pay ₦{amount:,.0f}", type="primary", use_container_width=True)
        st.caption("Card, bank transfer or USSD, secured by Paystack. The money goes straight to your gym.")
        if go:
            url, msg = start(sc, m, plan, amount, _email_for(m, email), auto)
            if not url:
                st.error(msg)
                return
            st.link_button("Continue to secure payment", url, type="primary", use_container_width=True)
            st.markdown(f'<meta http-equiv="refresh" content="0; url={url}">', unsafe_allow_html=True)


def render_done(params):
    """Paystack sends the member back here: confirm and show the result."""
    import gympulse_booking as gb
    gb._header()
    col = gw.center("memberpay_done", 560)
    with col:
        ref = params.get("reference") or params.get("trxref")
        if not ref:
            st.error("We couldn't find your payment. If money left your account, your gym will confirm it.")
            return
        ok, msg, info = apply(ref)
        if ok:
            gw._md(f'<div class="bk-title">Thank you, {gw._esc(info.get("first", ""))}.</div>'
                   f'<div class="bk-sub">{gw._esc(msg)}'
                   + (" Automatic renewal is on; you can stop it from the same link any time." if info.get("auto") else "")
                   + f' See you at {gw._esc(info.get("gym", "the gym"))}.</div>')
        else:
            st.info(msg)
