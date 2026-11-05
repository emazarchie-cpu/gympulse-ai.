"""GymPulse AI · Free trial, plans and subscriptions.

Every gym gets a 30-day free trial from the day it signs up (gyms that existed
before billing was switched on get 30 days from that day). The trial includes
every feature. When it ends there are no extra days: an Upgrade pop-up lists
the plans and the gym sees only the Subscription page until it pays. Its data
is kept, never deleted.

Plans (name, prices, who it's for, which features) are set by the founder in
Admin → Billing. Higher plans unlock more pages (PAGE_LEVEL). Gyms pay online
with Paystack (PAYSTACK_SECRET_KEY): the payment is checked with Paystack and
the subscription switches on by itself. Bank transfer stays as a fallback; the
founder confirms those in Admin.
Tables: sql/phase10_billing.sql. If the SQL hasn't been run, nothing is locked.
"""
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

TRIAL_DAYS = 30
GRACE_DAYS = 0          # locks the moment the 30th day ends (owners get emails before that)
ALWAYS_OPEN = ("Subscription", "Settings", "FAQs", "Admin")
PAYSTACK_API = "https://api.paystack.co"

# Feature levels. A plan's "access" picks one; higher plans include everything below.
LEVELS = {1: "Essentials", 2: "Growth tools", 3: "Everything"}
FEATURES = {
    1: ["Member records, plans and spreadsheet import",
        "Front-desk and QR check-in",
        "Payments and renewal tracking",
        "Risk Radar: see who has stopped coming, and why",
        "Follow-ups board for your staff",
        "Automatic renewal reminder emails with your logo",
        "Monthly report of members and money kept"],
    2: ["Action Centre: the best next step for every member",
        "Grow: campaigns, loyalty points, referrals and challenges",
        "Automatic \"we missed you\" and reward emails",
        "Business Insights: revenue, renewals and trends"],
    3: ["Archie, your AI retention assistant",
        "Model insights: why each member was flagged",
        "Priority WhatsApp support",
        "Help importing your members and setting up"],
}
PAGE_LEVEL = {"Action Centre": 2, "Grow": 2, "Business Insights": 2,
              "Archie": 3, "Model Insights": 3, "About the Model": 3}

DEFAULT_PLANS = [
    {"name": "Starter", "access": 1, "monthly": 15000, "yearly": 150000, "for_who": "Up to 100 members",
     "tagline": "Track every member and catch quiet drop-offs early.", "popular": False},
    {"name": "Growth", "access": 2, "monthly": 30000, "yearly": 300000, "for_who": "Up to 300 members",
     "tagline": "Win members back and keep them with rewards.", "popular": True},
    {"name": "Pro", "access": 3, "monthly": 50000, "yearly": 500000, "for_who": "300+ members",
     "tagline": "Every tool, plus Archie, your AI retention assistant.", "popular": False},
]
DEFAULT_PRICING = {"plans": [], "monthly": None, "yearly": None, "currency": "NGN", "pay_link": "",
                   "bank_name": "", "bank_account": "", "bank_holder": "",
                   "contact_whatsapp": "", "contact_email": "emmanuel@usegympulseai.com",
                   "note": "Founding gyms keep their price for life."}


def _num(x):
    try:
        v = float(x)
        return v if v == v and v > 0 else None
    except (TypeError, ValueError):
        return None


def plans(p):
    """The plans from Admin → Billing (or the starting plans): name, access, monthly, yearly, for_who, tagline, popular."""
    raw = [x for x in (p.get("plans") or []) if gw._text(x.get("name")) and (_num(x.get("monthly")) or _num(x.get("yearly")))]
    if not raw and _num(p.get("monthly")):           # a single price set before plans existed
        raw = [{"name": "Standard", "monthly": p["monthly"], "yearly": p.get("yearly"), "access": 3}]
    if not raw:
        raw = DEFAULT_PLANS
    out = []
    for i, x in enumerate(raw):
        mo, yr = _num(x.get("monthly")), _num(x.get("yearly"))
        try:
            access = max(1, min(3, int(x.get("access") or min(i + 1, 3))))
        except (TypeError, ValueError):
            access = min(i + 1, 3)
        out.append({"name": gw._text(x.get("name")).strip(), "access": access, "monthly": mo,
                    "yearly": yr or (mo * 10 if mo else None), "for_who": gw._text(x.get("for_who")).strip(),
                    "tagline": gw._text(x.get("tagline")).strip(), "popular": bool(x.get("popular"))})
    return out


def features(ps, i):
    """(heading, [benefits]) for plan i: its own level, with 'Everything in X, plus' for higher plans."""
    level = ps[i]["access"]
    below = [x for x in ps[:i] if x["access"] < level]
    if below and level > 1:
        return f"Everything in {below[-1]['name']}, plus:", sum((FEATURES[l] for l in range(below[-1]["access"] + 1, level + 1)), [])
    return "What's included:", sum((FEATURES[l] for l in range(1, level + 1)), [])


def yearly_saving(ps):
    """'2 months free' style label for the yearly option."""
    months = [12 - x["yearly"] / x["monthly"] for x in ps if x.get("monthly") and x.get("yearly")]
    if not months or min(months) <= 0.4:
        return ""
    m = round(min(months))
    return f"{m} month{'s' if m != 1 else ''} free" if m >= 1 else ""


def price_for(plan, period):
    return plan.get("yearly") if period == "yearly" else plan.get("monthly")


def _money(x):
    return f"₦{float(x):,.0f}" if x not in (None, "") else "–"


# ------------------------------------------------------------------ data
def pricing(supabase):
    def fetch():
        try:
            rows = supabase.table("platform_settings").select("value").eq("key", "pricing").limit(1).execute().data
            return {**DEFAULT_PRICING, **(rows[0]["value"] if rows else {})}
        except Exception:
            return dict(DEFAULT_PRICING)
    return gw._cached(("billing_pricing",), fetch, ttl=300)


def subscription(supabase, gym_id):
    """The gym's subscription row, or None when billing tables aren't set up (never lock then)."""
    def fetch():
        try:
            rows = supabase.table("gym_subscriptions").select("*").eq("gym_id", gym_id).limit(1).execute().data
            return rows[0] if rows else {}
        except Exception:
            return None
    return gw._cached(("billing_sub", gym_id), fetch, ttl=120)


def _d(value):
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except Exception:
        return None


def state(sub, today=None):
    """{"status", "days_left", "ends", "locked", "label"} for a subscription row."""
    today = today or gw.today_local()
    if sub is None:                                   # billing not set up: never lock
        return {"status": "off", "days_left": None, "ends": None, "locked": False, "label": ""}
    status = sub.get("status") or "trial"
    if status == "free":
        return {"status": "free", "days_left": None, "ends": None, "locked": False, "label": "Free access"}
    paid_until = _d(sub.get("paid_until"))
    if status == "active" and paid_until and paid_until >= today:
        return {"status": "active", "days_left": (paid_until - today).days, "ends": paid_until, "locked": False,
                "label": f"Subscribed until {paid_until:%d %b %Y}"}
    trial_end = _d(sub.get("trial_ends_on")) or (today + timedelta(days=TRIAL_DAYS))
    if status == "trial" and trial_end >= today:
        left = (trial_end - today).days
        return {"status": "trial", "days_left": left, "ends": trial_end, "locked": False,
                "label": f"Free trial: {left} day{'s' if left != 1 else ''} left"}
    ended = paid_until if status == "active" and paid_until else trial_end
    over = (today - ended).days
    return {"status": "expired", "days_left": -over, "ends": ended, "locked": over > GRACE_DAYS,
            "label": ("Your free trial has ended" if status == "trial" else "Your subscription has ended")}


def is_admin_account():
    try:
        import gympulse_admin as gadm
        return gadm.is_admin()
    except Exception:
        return False


# ------------------------------------------------------------------ in the app
def render_banner(supabase, gym_id):
    """No line at the top: owners are reminded by email. Shows the Upgrade pop-up once the trial is over."""
    s = state(subscription(supabase, gym_id))
    if s["locked"] and not is_admin_account() and not st.session_state.get("_upgrade_shown"):
        st.session_state["_upgrade_shown"] = True
        sub = subscription(supabase, gym_id) or {}
        (renew_dialog if sub.get("status") == "active" else upgrade_dialog)(pricing(supabase), s)
    return s


def period_picker(ps, key):
    """Monthly / Yearly switch. Returns 'monthly' or 'yearly'."""
    save = yearly_saving(ps)
    if not any(x.get("yearly") for x in ps):
        return "monthly"
    pick = st.segmented_control("Billing", ["monthly", "yearly"], default="monthly", key=key,
                                label_visibility="collapsed",
                                format_func=lambda v: "Monthly" if v == "monthly" else
                                ("Yearly · " + save if save else "Yearly"))
    return pick or "monthly"


def _price_line(plan, period):
    amount = price_for(plan, period)
    if not amount:
        return "", "", ""
    if period == "yearly":
        sub = f"{_money(amount / 12)} a month, billed {_money(amount)} once a year"
        if plan.get("monthly"):
            saved = plan["monthly"] * 12 - amount
            if saved > 0:
                sub += f" · you save {_money(saved)}"
        return _money(amount), "/ year", sub
    return _money(amount), "/ month", "Billed monthly. Cancel any time."


def _plan_cards(p, period="monthly", pay=None, key="pc"):
    """Plan cards inside the app. pay(plan) is called when a Choose button is pressed."""
    ps = plans(p)
    cols = st.columns(len(ps) if len(ps) <= 3 else 3)
    for i, plan in enumerate(ps):
        with cols[i % len(cols)].container(border=True):
            if plan.get("popular"):
                gw._md(gw.chip("Most popular", "lime"))
            st.markdown(f"#### {gw._esc(plan['name'])}")
            if plan.get("tagline"):
                st.caption(gw._esc(plan["tagline"]))
            line = _price_line(plan, period)
            if line[0]:
                st.markdown(f"<div style='font-size:30px;font-weight:800;line-height:1.1'>{line[0]}"
                            f"<span style='font-size:14px;font-weight:500;opacity:.7'> {line[1]}</span></div>",
                            unsafe_allow_html=True)
                st.caption(line[2])
            if plan.get("for_who"):
                st.markdown(f"**{gw._esc(plan['for_who'])}**")
            if pay:
                pay(plan, period, i)
            head, items = features(ps, i)
            st.caption(head)
            st.markdown("  \n".join(f":green[✓] {gw._esc(f)}" for f in items))


def _upgrade_body(p, s):
    st.markdown("Pick a plan to keep using GymPulse AI. **All your members, check-ins and reports are saved**, "
                "and you'll pick up right where you left off.")
    ps = plans(p)
    period = period_picker(ps, "upg_period")
    _plan_cards(p, period, key="upg")
    if st.button("Upgrade now", type="primary", use_container_width=True, icon=":material/rocket_launch:"):
        st.session_state["navigate_to"] = "Subscription"
        st.session_state["bill_period"] = period
        st.rerun()


@st.dialog("Your free trial has ended", width="large")
def upgrade_dialog(p, s):
    _upgrade_body(p, s)


@st.dialog("Your plan has ended", width="large")
def renew_dialog(p, s):
    _upgrade_body(p, s)


# ------------------------------------------------------------------ plan levels
def access_level(sub, ps):
    """Which features a gym can use: 3 (everything) on trial or free access, the plan's level when paying."""
    s = state(sub)
    if s["status"] != "active":
        return 3
    name = gw._text((sub or {}).get("plan")).split(" · ")[0].strip().lower()
    hit = next((x for x in ps if x["name"].lower() == name), None)
    return hit["access"] if hit else 3


def page_allowed(supabase, gym_id, page):
    need = PAGE_LEVEL.get(page, 1)
    if need <= 1 or is_admin_account():
        return True
    return access_level(subscription(supabase, gym_id), plans(pricing(supabase))) >= need


def render_upsell(supabase, gym_id, page):
    """Shown instead of a page that the gym's plan doesn't include."""
    ps = plans(pricing(supabase))
    need = PAGE_LEVEL.get(page, 1)
    plan = next((x for x in ps if x["access"] >= need), None)
    gw.page_header(page, "Not included in your current plan.", "Upgrade")
    with st.container(border=True):
        st.markdown(f"#### {gw._esc(page)} is part of the {gw._esc(plan['name']) if plan else 'higher'} plan")
        st.markdown("Upgrade to unlock it. Everything else keeps working, and your data stays as it is.")
        st.markdown("  \n".join(f":green[✓] {gw._esc(f)}" for f in FEATURES[need]))
        if st.button("See plans and upgrade", type="primary", icon=":material/rocket_launch:", key="upsell_go"):
            st.session_state["navigate_to"] = "Subscription"
            st.rerun()


# ------------------------------------------------------------------ website
def public_pricing():
    """Prices for the signed-out website (read with the server key, kept 5 minutes)."""
    def fetch():
        try:
            sc = _service()
            rows = sc.table("platform_settings").select("value").eq("key", "pricing").limit(1).execute().data if sc else []
            return {**DEFAULT_PRICING, **(rows[0]["value"] if rows else {})}
        except Exception:
            return dict(DEFAULT_PRICING)
    return gw._cached(("public_pricing",), fetch, ttl=300)


def landing_cards_html(ps, period, icon):
    cards = []
    for i, plan in enumerate(ps):
        price, unit, sub = _price_line(plan, period)
        head, items = features(ps, i)
        cards.append(
            f'<div class="lx-plan{" pop" if plan.get("popular") else ""}">'
            + ('<div class="lx-plan-badge">Most popular</div>' if plan.get("popular") else "")
            + f'<h4>{gw._esc(plan["name"])}</h4><div class="lx-plan-tag">{gw._esc(plan.get("tagline"))}</div>'
            + (f'<div class="lx-plan-price">{price} <small>{unit}</small></div><div class="lx-plan-sub">{sub}</div>'
               if price else '<div class="lx-plan-price">Ask us</div><div class="lx-plan-sub"></div>')
            + (f'<div class="lx-plan-who">{gw._esc(plan["for_who"])}</div>' if plan.get("for_who") else "")
            + f'<a class="lx-btn{" lx-btn-primary" if plan.get("popular") else ""}" href="#get-started">'
              f'Start 30 days free</a>'
            + f'<div class="lx-plan-head">{gw._esc(head)}</div><ul>'
            + "".join(f"<li>{icon('check', 15)}<span>{gw._esc(f)}</span></li>" for f in items)
            + "</ul></div>")
    return f'<div class="lx-plans" style="--n:{min(len(ps), 3)}">' + "".join(cards) + "</div>"


def render_landing_pricing(icon):
    p = public_pricing()
    ps = plans(p)
    gw._md("""<div class="lx-sec" id="pricing" style="padding-bottom:0">
      <div class="lx-kicker">Pricing</div>
      <div class="lx-h2">Try everything free for 30 days</div>
      <div class="lx-sub" style="margin-bottom:18px">Every plan starts with a 30-day free trial of every feature.
        No card needed. Pick a plan when your trial ends, and pay monthly or yearly.</div></div>""")
    with st.container(key="lx_period"):
        period = period_picker(ps, "lx_period_pick")
    gw._md(landing_cards_html(ps, period, icon)
           + f'<div class="lx-plan-foot">Prices in naira. Pay by card, bank transfer or USSD. '
             f'{gw._esc(p.get("note") or "")}</div>')


def must_lock(supabase, gym_id):
    return state(subscription(supabase, gym_id))["locked"] and not is_admin_account()


def _email_founder(subject, text, reply_to=None, to=None):
    import gympulse_admin as gadm
    import requests
    key = gadm._env("RESEND_API_KEY")
    if not key:
        return False
    try:
        r = requests.post("https://api.resend.com/emails", timeout=20, headers={"Authorization": f"Bearer {key}"},
                          json={"from": gadm._env("REPORTS_FROM", gadm.REPORTS_FROM_DEFAULT),
                                "to": [to or "emmanuel@usegympulseai.com"], "reply_to": reply_to or None,
                                "subject": subject, "text": text})
        return r.status_code < 300
    except Exception:
        return False


def _notify_paid(supabase, gym_id, method, ref):
    """Email the founder that a gym says it has paid by transfer, so they can confirm it in Admin."""
    profile = st.session_state.get("user_profile") or {}
    gym = gw._text(profile.get("business_name"), "A gym")
    owner = (st.session_state.get("auth_user") or {}).get("email", "")
    to = pricing(supabase).get("contact_email") or "emmanuel@usegympulseai.com"
    ok = _email_founder(f"Payment to confirm: {gym}",
                        f"{gym} ({owner}) says they've paid for GymPulse AI.\nMethod: {method}\n"
                        f"Reference: {ref or '-'}\nGym id: {gym_id}\n\nConfirm it in Admin → Billing.",
                        reply_to=owner, to=to)
    st.session_state["bill_flash"] = ("Thanks! We've let the GymPulse AI team know. Your subscription will be "
                                      "switched on as soon as the payment is confirmed (usually the same day)."
                                      if ok else "Thanks! Please also send your receipt to " + to + ".")


# ------------------------------------------------------------------ Paystack
def paystack_key():
    import gympulse_admin as gadm
    return gadm._env("PAYSTACK_SECRET_KEY")


def _paystack(method, path, **kw):
    import requests
    r = requests.request(method, PAYSTACK_API + path, timeout=25,
                         headers={"Authorization": f"Bearer {paystack_key()}"}, **kw)
    try:
        return r.json()
    except Exception:
        return {"status": False, "message": f"Paystack error {r.status_code}"}


def start_payment(gym_id, plan, period, email):
    """Create a Paystack checkout for this gym and plan. Returns (url, reference) or (None, error)."""
    import gympulse_email as ge
    amount = price_for(plan, period)
    if not (paystack_key() and amount and email):
        return None, "Online payment isn't set up yet."
    ref = f"gp-{str(gym_id)[:8]}-{uuid.uuid4().hex[:12]}"
    r = _paystack("POST", "/transaction/initialize", json={
        "email": email, "amount": int(round(amount * 100)), "currency": "NGN", "reference": ref,
        "callback_url": f"{ge.SITE}/?paystack=1",
        "metadata": {"source": "gympulse", "gym_id": str(gym_id), "plan": plan["name"], "period": period,
                     "cancel_action": f"{ge.SITE}/?p=Subscription"}})
    if r.get("status") and (r.get("data") or {}).get("authorization_url"):
        return r["data"]["authorization_url"], ref
    return None, r.get("message") or "Couldn't start the payment. Please try again."


def _service():
    import gympulse_admin as gadm
    return gadm.service_client()


def apply_payment(reference, sc=None):
    """Check a payment with Paystack and switch the gym's plan on. Safe to call many times.

    Returns (ok, message). The amount must match the plan's current price, and each
    payment is used once (billing_events ref paystack:<reference>).
    """
    sc = sc or _service()
    if not (sc and paystack_key() and reference):
        return False, "We couldn't check the payment right now. If you paid, it will show within a day."
    r = _paystack("GET", f"/transaction/verify/{quote(str(reference), safe='')}")
    d = r.get("data") or {}
    if not r.get("status") or d.get("status") != "success":
        return False, "That payment hasn't gone through yet. If money left your account, it will show here shortly."
    md = d.get("metadata") or {}
    if isinstance(md, str):
        try:
            md = json.loads(md)
        except Exception:
            md = {}
    gid, period = md.get("gym_id"), "yearly" if md.get("period") == "yearly" else "monthly"
    if md.get("source") != "gympulse" or not gid:
        return False, "That payment isn't for a GymPulse AI plan."
    rows = sc.table("platform_settings").select("value").eq("key", "pricing").limit(1).execute().data
    p = {**DEFAULT_PRICING, **(rows[0]["value"] if rows else {})}
    plan = next((x for x in plans(p) if x["name"] == md.get("plan")), None)
    paid = (d.get("amount") or 0) / 100
    expected = price_for(plan, period) if plan else None
    if d.get("currency") != "NGN" or not expected or paid + 0.5 < expected:
        _email_founder(f"Paystack payment to check: {reference}",
                       f"A payment of ₦{paid:,.0f} ({md.get('plan')}, {period}) for gym {gid} didn't match the "
                       f"current price ({_money(expected)}). Check it in Paystack, then use Mark as paid in Admin.")
        return False, "We've received your payment and the team will confirm it shortly."
    try:
        sc.table("billing_events").insert({"gym_id": gid, "kind": "paystack", "ref": f"paystack:{reference}"}).execute()
    except Exception:
        return True, "Payment received. Your plan is active."          # already applied
    today = gw.today_local()
    sub = (sc.table("gym_subscriptions").select("*").eq("gym_id", gid).limit(1).execute().data or [{}])[0]
    base = today
    if sub.get("status") == "active" and _d(sub.get("paid_until")):
        base = max(base, _d(sub.get("paid_until")))
    elif sub.get("status") == "trial" and _d(sub.get("trial_ends_on")):
        base = max(base, _d(sub.get("trial_ends_on")))       # paying early keeps the rest of the free trial
    until = base + timedelta(days=365 if period == "yearly" else 30)
    try:
        sc.table("gym_subscriptions").upsert({
            "gym_id": gid, "status": "active", "paid_until": until.isoformat(),
            "plan": f"{plan['name']} · {'Yearly' if period == 'yearly' else 'Monthly'}",
            "price": round(paid / 12 if period == "yearly" else paid, 2),
            "note": f"Paystack {reference}", "updated_at": datetime.now(timezone.utc).isoformat()},
            on_conflict="gym_id").execute()
    except Exception:
        sc.table("billing_events").delete().eq("gym_id", gid).eq("ref", f"paystack:{reference}").execute()
        raise
    email = (d.get("customer") or {}).get("email", "")
    _email_founder(f"New payment: {plan['name']} {period} · ₦{paid:,.0f}",
                   f"{email} paid ₦{paid:,.0f} for GymPulse AI {plan['name']} ({period}).\n"
                   f"Gym id: {gid}\nPaid until: {until:%d %b %Y}\nPaystack reference: {reference}")
    try:
        st.session_state.pop("_cache", None)
    except Exception:
        pass
    return True, f"Payment received, thank you! Your {plan['name']} plan is active until {until:%d %B %Y}."


def reconcile_paystack(sc, days=3, log=print):
    """Apply any successful Paystack payments from the last few days that weren't applied yet."""
    if not paystack_key():
        log("PAYSTACK_SECRET_KEY not set: skipped")
        return 0
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
    r = _paystack("GET", "/transaction", params={"status": "success", "from": since, "perPage": 100})
    done = {x["ref"] for x in sc.table("billing_events").select("ref").eq("kind", "paystack").execute().data or []}
    n = 0
    for t in r.get("data") or []:
        md = t.get("metadata") or {}
        if isinstance(md, str):
            try:
                md = json.loads(md)
            except Exception:
                md = {}
        if md.get("source") != "gympulse" or f"paystack:{t.get('reference')}" in done:
            continue
        ok, msg = apply_payment(t.get("reference"), sc)
        log(f"  {t.get('reference')}: {msg}")
        n += ok
    return n


def handle_return(params):
    """Paystack sends the payer back to ?paystack=1&reference=... Check it and remember the message."""
    ref = params.get("reference") or params.get("trxref")
    if not ref:
        return
    try:
        ok, msg = apply_payment(ref)
    except Exception as error:
        ok, msg = False, "We couldn't check the payment right now. If you paid, it will show within a day."
        try:
            import gympulse_monitoring as gmon
            gmon.capture(error, "paystack return")
        except Exception:
            pass
    st.session_state["bill_flash"] = msg
    st.session_state["bill_flash_ok"] = ok
    st.session_state.pop("_cache", None)
    st.session_state.pop("_upgrade_shown", None)


def _pay_button(supabase, gym_id):
    email = (st.session_state.get("auth_user") or {}).get("email", "")

    def pay(plan, period, i):
        if not price_for(plan, period):
            return
        pending = st.session_state.get("bill_checkout") or {}
        if pending.get("plan") == plan["name"] and pending.get("period") == period:
            st.link_button(f"Pay {_money(price_for(plan, period))} with Paystack", pending["url"], type="primary",
                           icon=":material/lock:", use_container_width=True)
            st.caption("Opens Paystack's secure checkout: card, bank transfer or USSD.")
            return
        if st.button(f"Choose {plan['name']}", key=f"bill_choose_{i}_{period}", use_container_width=True,
                     type="primary" if plan.get("popular") else "secondary"):
            url, ref = start_payment(gym_id, plan, period, email)
            if url:
                st.session_state["bill_checkout"] = {"plan": plan["name"], "period": period, "url": url, "ref": ref}
            else:
                st.session_state["bill_flash"], st.session_state["bill_flash_ok"] = ref, False
            st.rerun()
    return pay


def render_subscription_page(supabase, gym_id):
    gw.page_header("Subscription", "Your GymPulse AI plan.", "Account")
    flash = st.session_state.pop("bill_flash", None)
    if flash:
        (st.success if st.session_state.pop("bill_flash_ok", True) else st.warning)(flash)
    s = state(subscription(supabase, gym_id))
    p = pricing(supabase)
    if s["status"] == "off":
        st.info("Billing isn't switched on yet. Enjoy GymPulse AI free.")
        return
    if s["locked"]:
        st.error(("Your free trial has ended." if (subscription(supabase, gym_id) or {}).get("status") != "active"
                  else "Your plan has ended.") + " Pick a plan below to keep using GymPulse AI. Everything you "
                 "added is safe, and you'll pick up right where you left off.")
    sub = subscription(supabase, gym_id) or {}
    gw.kpi_row([("Your plan", {"trial": "Free trial", "active": gw._text(sub.get("plan"), "Subscribed"),
                              "free": "Free access", "expired": "Ended"}[s["status"]], "lime", s["label"]),
                ("Ends", f"{s['ends']:%d %b %Y}" if s.get("ends") else "–", "grey", "")])
    if s["status"] == "free":
        st.success("Your gym has free access to GymPulse AI. Nothing to pay.")
        return
    if s["status"] == "trial":
        st.caption("Your free trial includes every feature. Pay now or any time before it ends: your paid plan "
                   "starts when the trial finishes, so you don't lose any free days.")

    pending = st.session_state.get("bill_checkout")
    if pending and st.button("I've finished paying: check my payment", icon=":material/refresh:", key="bill_check"):
        ok, msg = apply_payment(pending["ref"])
        st.session_state["bill_flash"], st.session_state["bill_flash_ok"] = msg, ok
        if ok:
            st.session_state.pop("bill_checkout", None)
        st.rerun()

    st.markdown("#### Plans")
    ps = plans(p)
    if "bill_period" in st.session_state and "sub_period" not in st.session_state:
        st.session_state["sub_period"] = st.session_state.pop("bill_period")
    period = period_picker(ps, "sub_period")
    online = bool(paystack_key())
    _plan_cards(p, period, pay=_pay_button(supabase, gym_id) if online else None, key="sub")
    if p.get("note"):
        st.caption(p["note"])

    contact = []
    if p.get("contact_whatsapp"):
        contact.append(f"WhatsApp {p['contact_whatsapp']}")
    if p.get("contact_email"):
        contact.append(p["contact_email"])
    other = p.get("bank_account") or p.get("pay_link") or not online
    if other:
        with st.expander("Other ways to pay" if online else "How to pay", expanded=not online):
            if p.get("pay_link"):
                st.link_button("Pay with a payment link", p["pay_link"], icon=":material/link:")
            if p.get("bank_account"):
                st.markdown(f"**Bank transfer:** {p.get('bank_name', '')} · {p['bank_account']} · "
                            f"{p.get('bank_holder', '')}  \nUse your gym's name as the reference.")
            with st.form("bill_paid"):
                st.markdown("**Paid by transfer?** Tell us and we'll switch your plan on.")
                c0, c1, c2 = st.columns(3)
                plan_pick = c0.selectbox("Plan", [x["name"] for x in ps])
                method = c1.selectbox("How did you pay?", ["Bank transfer", "Online payment link", "Other"])
                ref = c2.text_input("Reference or note (optional)")
                if st.form_submit_button("I've paid", type="primary"):
                    _notify_paid(supabase, gym_id, method, f"{plan_pick} · {period} · {ref.strip()}".strip(" ·"))
                    st.rerun()
    if contact:
        st.caption("Questions? " + " · ".join(contact))


# ------------------------------------------------------------------ admin
def admin_set(sc, gym_id, **fields):
    sc.table("gym_subscriptions").upsert({"gym_id": gym_id, **fields,
                                         "updated_at": datetime.now(timezone.utc).isoformat()},
                                        on_conflict="gym_id").execute()
    st.session_state.pop("_cache", None)


def render_admin_billing(sc, gyms, audit):
    """Admin → Billing: prices, payment details, and each gym's plan."""
    today = gw.today_local()
    try:
        subs = {r["gym_id"]: r for r in sc.table("gym_subscriptions").select("*").execute().data or []}
        rows = sc.table("platform_settings").select("value").eq("key", "pricing").limit(1).execute().data
        p = {**DEFAULT_PRICING, **(rows[0]["value"] if rows else {})}
    except Exception:
        st.info("Run sql/phase10_billing.sql in Supabase to switch on free trials and subscriptions.")
        return
    states = {g["gym"]["id"]: state(subs.get(g["gym"]["id"], {}), today) for g in gyms}
    gw.kpi_row([("On free trial", str(sum(s["status"] == "trial" for s in states.values())), "cyan", f"{TRIAL_DAYS} days"),
                ("Paying", str(sum(s["status"] == "active" for s in states.values())), "lime", ""),
                ("Ended, not paid", str(sum(s["status"] == "expired" for s in states.values())), "red", "follow up"),
                ("Monthly income", _money(sum(float(subs.get(gid, {}).get("price") or 0) for gid, s in states.items()
                                              if s["status"] == "active")), "amber", "from paying gyms")])

    with st.expander("Plans, prices and how gyms pay", expanded=not plans(p)):
        with st.form("adm_pricing"):
            st.markdown("**Your plans.** One row per plan, cheapest first. Gyms see these on the website, in the "
                        "Upgrade pop-up and on their Subscription page. **Features** sets what each plan unlocks; "
                        "the benefits list is written for you. Leave the yearly price blank for 2 months free.")
            level_names = {1: "1 · Essentials", 2: "2 · + Growth tools", 3: "3 · Everything"}
            start_rows = [{**x, "access": level_names[x["access"]]} for x in plans(p)]
            plan_rows = st.data_editor(
                pd.DataFrame(start_rows, columns=["name", "access", "monthly", "yearly", "for_who", "tagline", "popular"]),
                num_rows="dynamic", use_container_width=True, key="adm_plans",
                column_config={"name": st.column_config.TextColumn("Plan name", required=True),
                               "access": st.column_config.SelectboxColumn("Features", options=list(level_names.values()),
                                                                          required=True),
                               "monthly": st.column_config.NumberColumn("Monthly (₦)", min_value=0, step=1000),
                               "yearly": st.column_config.NumberColumn("Yearly (₦)", min_value=0, step=5000),
                               "for_who": st.column_config.TextColumn("Who it's for"),
                               "tagline": st.column_config.TextColumn("One-line description"),
                               "popular": st.column_config.CheckboxColumn("Most popular")})
            st.caption("  \n".join(f"**{label}**{' adds' if lv > 1 else ''}: " + "; ".join(FEATURES[lv])
                                   for lv, label in level_names.items()))
            link = st.text_input("Online payment link (optional)", p.get("pay_link") or "",
                                 placeholder="e.g. your Paystack payment page")
            c3, c4, c5 = st.columns(3)
            bank = c3.text_input("Bank", p.get("bank_name") or "")
            acct = c4.text_input("Account number", p.get("bank_account") or "")
            holder = c5.text_input("Account name", p.get("bank_holder") or "")
            c6, c7 = st.columns(2)
            wa = c6.text_input("Your WhatsApp for questions", p.get("contact_whatsapp") or "")
            em = c7.text_input("Email for payment notices", p.get("contact_email") or "")
            note = st.text_input("Short note under the price (optional)", p.get("note") or "")
            if st.form_submit_button("Save prices", type="primary"):
                plan_list = []
                for _, r in plan_rows.iterrows():
                    name = gw._text(r.get("name")).strip()
                    mo = float(r["monthly"]) if pd.notna(r.get("monthly")) and r.get("monthly") else None
                    yr = float(r["yearly"]) if pd.notna(r.get("yearly")) and r.get("yearly") else None
                    lv = next((k for k, v in level_names.items() if v == r.get("access")), 1)
                    if name and (mo or yr):
                        plan_list.append({"name": name, "access": lv, "monthly": mo, "yearly": yr,
                                          "for_who": gw._text(r.get("for_who")).strip(),
                                          "tagline": gw._text(r.get("tagline")).strip(),
                                          "popular": bool(r.get("popular")) if pd.notna(r.get("popular")) else False})
                value = {"plans": plan_list, "monthly": None, "yearly": None, "currency": "NGN",
                         "pay_link": link.strip(), "bank_name": bank.strip(), "bank_account": acct.strip(),
                         "bank_holder": holder.strip(), "contact_whatsapp": wa.strip(),
                         "contact_email": em.strip(), "note": note.strip()}
                sc.table("platform_settings").upsert({"key": "pricing", "value": value,
                                                      "updated_at": datetime.now(timezone.utc).isoformat()},
                                                     on_conflict="key").execute()
                st.session_state["adm_flash"] = "Plans saved. They now show on the website and in the app."
                st.rerun()

    with st.expander("Online payments (Paystack)"):
        if paystack_key():
            mode = "test mode" if paystack_key().startswith("sk_test") else "live"
            st.success(f"Paystack is connected ({mode}). Gyms can pay by card, transfer or USSD, and their plan "
                       "switches on by itself. Money goes to the bank account in your Paystack dashboard.")
            if st.button("Check Paystack for missed payments", key="adm_ps_sync"):
                n = reconcile_paystack(sc, days=14, log=lambda *_: None)
                st.session_state["adm_flash"] = f"Checked Paystack: {n} payment{'s' if n != 1 else ''} switched on."
                st.rerun()
        else:
            st.info("Not connected yet. Add your Paystack secret key as PAYSTACK_SECRET_KEY in Render "
                    "(Environment) and in GitHub (Settings → Secrets → Actions). See docs/BILLING.md.")

    order = {"expired": 0, "trial": 1, "active": 2, "free": 3, "off": 4}
    for g in sorted(gyms, key=lambda g: (order[states[g["gym"]["id"]]["status"]],
                                         states[g["gym"]["id"]].get("days_left") or 0)):
        gid = g["gym"]["id"]
        s, sub = states[gid], subs.get(gid, {})
        tone = {"trial": "cyan", "active": "lime", "free": "grey", "expired": "red"}.get(s["status"], "grey")
        with st.expander(f"{g['name']} · {s['label'] or 'no plan yet'}"):
            gw._md(gw.chip(s["status"], tone, dot=True) + (gw.chip("admin", "cyan") if (g.get("email") or "").lower()
                                                          in __import__("gympulse_admin").admin_emails() else ""))
            st.caption(f"Trial ends {sub.get('trial_ends_on') or '–'} · paid until {sub.get('paid_until') or '–'} · "
                       f"price {_money(sub.get('price'))}")
            ps = plans(p)
            names = [x["name"] for x in ps] or ["Standard"]
            current = gw._text(sub.get("plan")).split(" · ")[0]
            c0, c1, c2, c3 = st.columns(4)
            plan_name = c0.selectbox("Plan", names, index=names.index(current) if current in names else 0,
                                     key=f"bill_plan_{gid}")
            chosen = next((x for x in ps if x["name"] == plan_name), {})
            months = c1.selectbox("Paid for", [1, 3, 6, 12], key=f"bill_m_{gid}",
                                  format_func=lambda m: f"{m} month{'s' if m != 1 else ''}")
            price = c2.number_input("Monthly price for this gym (₦)", 0.0, step=1000.0,
                                    value=float(chosen.get("monthly") or sub.get("price") or 0),
                                    key=f"bill_p_{gid}_{plan_name}")
            if c3.button("Mark as paid", key=f"bill_paid_{gid}", type="primary", use_container_width=True):
                start = max(_d(sub.get("paid_until")) or today, today)
                until = start + timedelta(days=30 * months)
                admin_set(sc, gid, status="active", paid_until=until.isoformat(), price=price or None,
                          plan=f"{plan_name} · {months} month{'s' if months != 1 else ''}")
                audit(sc, "billing_paid", g, {"months": months, "until": until.isoformat(), "price": price})
                st.session_state["adm_flash"] = f"{g['name']} is subscribed until {until:%d %b %Y}."
                st.rerun()
            d1, d2, d3 = st.columns(3)
            if d1.button("Extend trial 14 days", key=f"bill_ext_{gid}", use_container_width=True):
                base = max(_d(sub.get("trial_ends_on")) or today, today)
                admin_set(sc, gid, status="trial", trial_ends_on=(base + timedelta(days=14)).isoformat())
                audit(sc, "billing_trial_extended", g, {"days": 14})
                st.session_state["adm_flash"] = f"{g['name']}'s trial now ends {(base + timedelta(days=14)):%d %b}."
                st.rerun()
            if d2.button("Give free access", key=f"bill_free_{gid}", use_container_width=True,
                         help="For test accounts, partners or friends. They are never asked to pay."):
                admin_set(sc, gid, status="free")
                audit(sc, "billing_free", g)
                st.session_state["adm_flash"] = f"{g['name']} now has free access."
                st.rerun()
            if s["status"] in ("active", "free") and d3.button("End subscription", key=f"bill_end_{gid}",
                                                              use_container_width=True):
                admin_set(sc, gid, status="trial", trial_ends_on=(today - timedelta(days=1)).isoformat(),
                          paid_until=None)
                audit(sc, "billing_ended", g)
                st.session_state["adm_flash"] = f"{g['name']}'s subscription has ended."
                st.rerun()


def gym_levels(sc):
    """{gym_id: feature level} for the scheduled jobs (3 when billing isn't set up)."""
    try:
        subs = sc.table("gym_subscriptions").select("*").execute().data or []
        rows = sc.table("platform_settings").select("value").eq("key", "pricing").limit(1).execute().data
        ps = plans({**DEFAULT_PRICING, **(rows[0]["value"] if rows else {})})
    except Exception:
        return {}
    return {r["gym_id"]: access_level(r, ps) for r in subs}


# ------------------------------------------------------------------ reminders (scheduled)
def trial_reminders(sc, gyms, dry_run=False, log=print):
    """Email owners 7, 3 and 1 days before their trial ends and the day after; paying gyms 3 and 1 days
    before their plan ends and the day after. Once each."""
    import gympulse_admin as gadm
    import gympulse_email as ge
    import requests
    today = gw.today_local()
    try:
        subs = {r["gym_id"]: r for r in sc.table("gym_subscriptions").select("*").execute().data or []}
        done = {(r["gym_id"], r["ref"]) for r in sc.table("billing_events").select("gym_id, ref").execute().data or []}
        rows = sc.table("platform_settings").select("value").eq("key", "pricing").limit(1).execute().data
        p = {**DEFAULT_PRICING, **(rows[0]["value"] if rows else {})}
    except Exception:
        log("billing tables missing: run sql/phase10_billing.sql")
        return 0
    key, sent = gadm._env("RESEND_API_KEY"), 0
    for g in gyms:
        gid, sub = g["gym"]["id"], subs.get(g["gym"]["id"])
        if not sub or sub.get("status") not in ("trial", "active") or "@" not in (g.get("email") or ""):
            continue
        if (g.get("email") or "").lower() in gadm.admin_emails():
            continue
        paying = sub.get("status") == "active"
        end = _d(sub.get("paid_until") if paying else sub.get("trial_ends_on"))
        if not end:
            continue
        left = (end - today).days
        stage = ({3: "3days", 1: "1day", -1: "ended"} if paying else {7: "7days", 3: "3days", 1: "1day", -1: "ended"}).get(left)
        kind = "renew" if paying else "trial"
        if not stage or (gid, f"{kind}:{stage}:{end}") in done:
            continue
        first = gw._text(g["owner"]).split(" ")[0] or "there"
        ps = plans(p)
        price = "Plans: " + "; ".join(f"{x['name']} {_money(x['monthly'])} a month" for x in ps if x.get("monthly")) + "."
        if paying:
            plan_name = gw._text(sub.get("plan"), "GymPulse AI").split(" · ")[0]
            price = ""
            if stage == "ended":
                subject, title = f"{g['name']}: your GymPulse AI plan has ended", "Your plan has ended"
                lead = (f"Your {plan_name} plan ended on {end:%A %d %B}. Your members, check-ins and reports are "
                        "all saved. Renew to pick up right where you left off.")
            else:
                days = {"3days": "3 days", "1day": "1 day"}[stage]
                subject, title = f"{g['name']}: your GymPulse AI plan ends in {days}", f"Your plan ends in {days}"
                lead = (f"Your {plan_name} plan ends on {end:%A %d %B}. Renew in a minute from the Subscription "
                        "page to keep your reminders, Risk Radar and reports running.")
        elif stage == "ended":
            subject, title = f"{g['name']}: your GymPulse AI free trial has ended", "Your free trial has ended"
            lead = ("Your 30-day free trial of GymPulse AI has ended. Your members, check-ins and reports are all "
                    "saved. Upgrade to pick up right where you left off.")
        else:
            days = {"7days": "7 days", "3days": "3 days", "1day": "1 day"}[stage]
            subject, title = f"{g['name']}: {days} left in your GymPulse AI trial", f"{days} left in your free trial"
            lead = (f"Your free trial of GymPulse AI ends on {end:%A %d %B}. Subscribe to keep your renewal "
                    "reminders, Risk Radar and monthly reports running without a break.")
        body = (f"<p style=\"margin:0 0 10px\">Hi {gw._esc(first)},</p><p style=\"margin:0 0 12px\">{gw._esc(lead)}</p>"
                + (f"<p style=\"margin:0 0 12px\">{gw._esc(price)}</p>" if price else "")
                + ge.button("Renew now" if paying else "See plans and upgrade", f"{ge.SITE}/?p=Subscription"))
        if dry_run:
            log(f"  would email {g['name']} <{g['email']}>: {subject}")
            sent += 1
            continue
        if not key:
            log("RESEND_API_KEY missing")
            return sent
        try:
            r = requests.post("https://api.resend.com/emails", timeout=20, headers={"Authorization": f"Bearer {key}"},
                              json={"from": gadm._env("REPORTS_FROM", gadm.REPORTS_FROM_DEFAULT), "to": [g["email"]],
                                    "reply_to": p.get("contact_email") or "emmanuel@usegympulseai.com",
                                    "subject": subject, "html": ge.layout(title, body, preheader=subject),
                                    "text": f"Hi {first},\n\n{lead}\n\n{price}\n\n{ge.SITE}"})
            if r.status_code < 300:
                sc.table("billing_events").insert({"gym_id": gid, "kind": f"{kind}_reminder",
                                                   "ref": f"{kind}:{stage}:{end}"}).execute()
                sent += 1
                log(f"  sent {kind} {stage} -> {g['name']}")
        except Exception as error:
            log(f"  failed {kind} {stage} -> {g['name']}: {error}")
    return sent
