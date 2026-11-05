"""GymPulse AI · Free trial and subscription.

Every gym gets a 30-day free trial from the day it signs up. Gyms that existed
before billing was switched on get 30 days from that day. When the trial ends,
there are 3 days' grace with a warning. After that the gym sees the
Subscription page until it pays (its data is kept, never deleted).

Prices and payment details are set by the founder in Admin → Billing, not in
code, and the founder marks gyms as paid (bank transfer or a payment link) or
gives a gym free access. Gym owners can read their own subscription row and
nothing else. Only the Admin page (service key) can change it.
Tables: sql/phase10_billing.sql.

If the SQL hasn't been run yet, nothing is ever locked.
"""
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

TRIAL_DAYS = 30
GRACE_DAYS = 0          # locks the moment the 30th day ends (owners get emails before that)
ALWAYS_OPEN = ("Subscription", "Settings", "FAQs", "Admin")
DEFAULT_PRICING = {"plans": [], "monthly": None, "yearly": None, "currency": "NGN", "pay_link": "",
                   "bank_name": "", "bank_account": "", "bank_holder": "",
                   "contact_whatsapp": "", "contact_email": "emmanuel@usegympulseai.com",
                   "note": "Founding gyms keep their price for life."}


def plans(p):
    """The plans the founder set in Admin → Billing: [{name, monthly, yearly, for_who}]."""
    out = [x for x in (p.get("plans") or []) if gw._text(x.get("name")) and (x.get("monthly") or x.get("yearly"))]
    if not out and p.get("monthly"):                 # a single price set before plans existed
        out = [{"name": "Standard", "monthly": p["monthly"], "yearly": p.get("yearly"), "for_who": ""}]
    return out


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
        upgrade_dialog(pricing(supabase), s)
    return s


def _plan_cards(p):
    ps = plans(p)
    if not ps:
        st.info("Prices are being finalised. Contact us and we'll set up your plan.")
        return
    cols = st.columns(min(len(ps), 3))
    for i, plan in enumerate(ps):
        with cols[i % len(cols)].container(border=True):
            st.markdown(f"#### {gw._esc(plan['name'])}")
            if plan.get("monthly"):
                st.markdown(f"## {_money(plan['monthly'])}<span style='font-size:14px;opacity:.7'> / month</span>",
                            unsafe_allow_html=True)
            if plan.get("yearly"):
                st.caption(f"or {_money(plan['yearly'])} a year")
            if plan.get("for_who"):
                st.caption(gw._esc(plan["for_who"]))


@st.dialog("Your free trial has ended", width="large")
def upgrade_dialog(p, s):
    st.markdown("Upgrade to keep using GymPulse AI. **All your members, check-ins and reports are saved**, and "
                "you'll pick up right where you left off.")
    _plan_cards(p)
    if st.button("Upgrade now", type="primary", use_container_width=True, icon=":material/rocket_launch:"):
        st.session_state["navigate_to"] = "Subscription"
        st.rerun()


def must_lock(supabase, gym_id):
    return state(subscription(supabase, gym_id))["locked"] and not is_admin_account()


def _notify_paid(supabase, gym_id, method, ref):
    """Email the founder that a gym says it has paid, so they can confirm it in Admin."""
    import gympulse_admin as gadm
    import requests
    profile = st.session_state.get("user_profile") or {}
    gym = gw._text(profile.get("business_name"), "A gym")
    owner = (st.session_state.get("auth_user") or {}).get("email", "")
    to = pricing(supabase).get("contact_email") or "emmanuel@usegympulseai.com"
    key = gadm._env("RESEND_API_KEY")
    if not key:
        st.session_state["bill_flash"] = "Thanks! We'll confirm your payment shortly."
        return
    body = (f"{gym} ({owner}) says they've paid for GymPulse AI.\nMethod: {method}\nReference: {ref or '-'}\n"
            f"Gym id: {gym_id}\n\nConfirm it in Admin → Billing.")
    try:
        requests.post("https://api.resend.com/emails", timeout=20, headers={"Authorization": f"Bearer {key}"},
                      json={"from": gadm._env("REPORTS_FROM", gadm.REPORTS_FROM_DEFAULT), "to": [to],
                            "reply_to": owner or None, "subject": f"Payment to confirm: {gym}", "text": body})
        st.session_state["bill_flash"] = ("Thanks! We've let the GymPulse AI team know. Your subscription will be "
                                          "switched on as soon as the payment is confirmed (usually the same day).")
    except Exception:
        st.session_state["bill_flash"] = "Thanks! Please also send your receipt to " + to + "."


def render_subscription_page(supabase, gym_id):
    gw.page_header("Subscription", "Your GymPulse AI plan.", "Account")
    flash = st.session_state.pop("bill_flash", None)
    if flash:
        st.success(flash)
    s = state(subscription(supabase, gym_id))
    p = pricing(supabase)
    if s["status"] == "off":
        st.info("Billing isn't switched on yet. Enjoy GymPulse AI free.")
        return
    if s["locked"]:
        st.error("Your free trial has ended. Upgrade below to keep using GymPulse AI. Everything you added is safe, "
                 "and you'll pick up right where you left off.")
    sub = subscription(supabase, gym_id) or {}
    gw.kpi_row([("Your plan", {"trial": "Free trial", "active": gw._text(sub.get("plan"), "Subscribed"),
                              "free": "Free access", "expired": "Ended"}[s["status"]], "lime", s["label"]),
                ("Ends", f"{s['ends']:%d %b %Y}" if s.get("ends") else "–", "grey", "")])
    if s["status"] != "free":
        st.markdown("#### Plans")
        _plan_cards(p)
    if s["status"] == "free":
        st.success("Your gym has free access to GymPulse AI. Nothing to pay.")
        return
    st.markdown("#### What you get")
    st.markdown("- Risk Radar: see who's about to stop coming, and why\n"
                "- Automatic renewal reminders and \"we missed you\" emails with your logo\n"
                "- Loyalty points, challenges, referrals and the full Grow toolkit\n"
                "- Archie, your retention assistant\n"
                "- A monthly report of the members and money you kept")
    if p.get("note"):
        st.caption(p["note"])
    st.markdown("#### How to pay")
    if p.get("pay_link"):
        st.link_button("Pay securely online", p["pay_link"], type="primary", icon=":material/lock:")
    if p.get("bank_account"):
        st.markdown(f"**Bank transfer:** {p.get('bank_name', '')} · {p['bank_account']} · {p.get('bank_holder', '')}  \n"
                    f"Use your gym's name as the reference.")
    contact = []
    if p.get("contact_whatsapp"):
        contact.append(f"WhatsApp {p['contact_whatsapp']}")
    if p.get("contact_email"):
        contact.append(p["contact_email"])
    if contact:
        st.caption("Questions? " + " · ".join(contact))
    with st.form("bill_paid"):
        st.markdown("**Already paid?** Tell us and we'll switch your subscription on.")
        names = [x["name"] for x in plans(p)] or ["Not sure yet"]
        c0, c1, c2 = st.columns(3)
        plan_pick = c0.selectbox("Plan", names)
        method = c1.selectbox("How did you pay?", ["Bank transfer", "Online payment link", "Other"])
        ref = c2.text_input("Reference or note (optional)")
        if st.form_submit_button("I've paid", type="primary"):
            _notify_paid(supabase, gym_id, method, f"{plan_pick} · {ref.strip()}".strip(" ·"))
            st.rerun()


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
            st.markdown("**Your plans** (add a row for each plan; gyms see them in the Upgrade pop-up)")
            start_rows = plans(p) or [{"name": "Starter", "monthly": None, "yearly": None, "for_who": "Up to 100 members"},
                                      {"name": "Growth", "monthly": None, "yearly": None, "for_who": "Up to 300 members"},
                                      {"name": "Pro", "monthly": None, "yearly": None, "for_who": "300+ members"}]
            plan_rows = st.data_editor(
                pd.DataFrame(start_rows, columns=["name", "monthly", "yearly", "for_who"]), num_rows="dynamic",
                use_container_width=True, key="adm_plans",
                column_config={"name": st.column_config.TextColumn("Plan name"),
                               "monthly": st.column_config.NumberColumn("Monthly price (₦)", min_value=0, step=1000),
                               "yearly": st.column_config.NumberColumn("Yearly price (₦, optional)", min_value=0, step=5000),
                               "for_who": st.column_config.TextColumn("Who it's for (shown under the price)")})
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
                    if name and (mo or yr):
                        plan_list.append({"name": name, "monthly": mo, "yearly": yr,
                                          "for_who": gw._text(r.get("for_who")).strip()})
                value = {"plans": plan_list, "monthly": None, "yearly": None, "currency": "NGN",
                         "pay_link": link.strip(), "bank_name": bank.strip(), "bank_account": acct.strip(),
                         "bank_holder": holder.strip(), "contact_whatsapp": wa.strip(),
                         "contact_email": em.strip(), "note": note.strip()}
                sc.table("platform_settings").upsert({"key": "pricing", "value": value,
                                                      "updated_at": datetime.now(timezone.utc).isoformat()},
                                                     on_conflict="key").execute()
                st.session_state["adm_flash"] = "Prices saved. Gyms see them on their Subscription page."
                st.rerun()

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


# ------------------------------------------------------------------ reminders (scheduled)
def trial_reminders(sc, gyms, dry_run=False, log=print):
    """Email owners 7, 3 and 1 days before their trial ends, and the day after it ends. Once each."""
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
        if not sub or sub.get("status") != "trial" or "@" not in (g.get("email") or ""):
            continue
        if (g.get("email") or "").lower() in gadm.admin_emails():
            continue
        end = _d(sub.get("trial_ends_on"))
        if not end:
            continue
        left = (end - today).days
        stage = {7: "7days", 3: "3days", 1: "1day", -1: "ended"}.get(left)
        if not stage or (gid, f"trial:{stage}:{end}") in done:
            continue
        first = gw._text(g["owner"]).split(" ")[0] or "there"
        ps = plans(p)
        price = ("Plans: " + "; ".join(f"{x['name']} {_money(x['monthly'])} a month" for x in ps if x.get("monthly"))
                 + ".") if ps else ""
        if stage == "ended":
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
                + ge.button("See plans and upgrade", ge.SITE))
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
                sc.table("billing_events").insert({"gym_id": gid, "kind": "trial_reminder",
                                                   "ref": f"trial:{stage}:{end}"}).execute()
                sent += 1
                log(f"  sent trial {stage} -> {g['name']}")
        except Exception as error:
            log(f"  failed trial {stage} -> {g['name']}: {error}")
    return sent
