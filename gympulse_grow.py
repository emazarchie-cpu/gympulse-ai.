"""GymPulse AI · Grow: tools that keep members and bring new ones in.

Collect renewals by transfer or payment link, the first 90 days programme,
freezes instead of cancellations, why members leave, progress tracking,
bring-a-friend referrals, group challenges, corporate memberships, the team
leaderboard, the Nigerian season planner and the monthly owner report.

Every number shown comes from recorded data: members, check-ins, payments
and plays. Nothing is estimated unless it says so.
Tables: sql/phase5_growth.sql.
"""
import calendar
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

SQL_HINT = "Run sql/phase5_growth.sql in Supabase to switch this on."

SECTIONS = ["Collect renewals", "Automatic messages", "Loyalty", "New members", "Freeze", "Why they left", "Progress",
            "Referrals", "Challenges", "Corporate", "Team", "Season planner", "Monthly report"]


# ================================================================== helpers
def _today():
    return gw.today_local()


def _first(name):
    return (gw._text(name).split() or ["there"])[0]


def _money(x):
    try:
        return f"₦{float(x):,.0f}"
    except Exception:
        return "₦0"


def _settings():
    p = st.session_state.get("user_profile") or {}
    return dict(p.get("settings") or {})


def _biz():
    p = st.session_state.get("user_profile") or {}
    return gw._text(p.get("business_name"), "our gym"), gw._text(p.get("full_name"), "")


def _rows(supabase, table, gym_id, order="created_at", desc=True):
    """All of a gym's rows from one table, or None when the table doesn't exist yet."""
    def fetch():
        try:
            q = supabase.table(table).select("*").eq("gym_id", gym_id)
            if order:
                q = q.order(order, desc=desc)
            return q.execute().data or []
        except Exception:
            return None
    return gw._cached(("grow", table, gym_id), fetch, ttl=30)


def _insert(supabase, table, row):
    try:
        supabase.table(table).insert(row).execute()
        gw.bump_data_version()
        return True
    except Exception as error:
        st.error(f"Could not save: {error}. {SQL_HINT}")
        return False


def _update(supabase, table, row_id, fields):
    try:
        supabase.table(table).update(fields).eq("id", row_id).execute()
        gw.bump_data_version()
        return True
    except Exception as error:
        st.error(f"Could not save: {error}")
        return False


def _delete(supabase, table, row_id):
    try:
        supabase.table(table).delete().eq("id", row_id).execute()
        gw.bump_data_version()
    except Exception as error:
        st.error(f"Could not remove: {error}")


def _members(supabase, gym_id):
    """Active members with join date, plan and fee (roster columns when available)."""
    df, _ = gw.fetch_members(supabase, gym_id, archived=False, include_photo=False)
    if df.empty:
        return df
    try:
        act = pd.DataFrame(supabase.table("member_activity").select("*").eq("gym_id", gym_id)
                           .execute().data or [])
    except Exception:
        act = pd.DataFrame()
    if not act.empty and "member_id" in act.columns:
        keep = [c for c in ("member_id", "membership_type", "monthly_fee", "renewal_due_days") if c in act.columns]
        df = df.merge(act[keep], left_on="id", right_on="member_id", how="left")
    for c in ("membership_type", "monthly_fee"):
        if c not in df.columns:
            df[c] = None
    df["monthly_fee"] = pd.to_numeric(df["monthly_fee"], errors="coerce").fillna(0)
    df["joined"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True, format="ISO8601") \
        .dt.tz_convert(gw.APP_TZ).dt.date
    df["end"] = pd.to_datetime(df["membership_end"], errors="coerce").dt.date
    return df


def _has_date(value):
    """True for a real date; False for None, NaN or NaT (members with no join or end date)."""
    return value is not None and not pd.isna(value)


def _member_names(df):
    return {r["id"]: gw._text(r.get("full_name"), "Member") for _, r in df.iterrows()} if len(df) else {}


def _checkins(supabase, gym_id, days=90):
    key = ("grow_ck", gym_id, days)
    ck = gw._cached(key, lambda: gw._fetch_checkins(supabase, gym_id, days=days), ttl=60)
    if ck is None:
        return pd.DataFrame(columns=["member_id", "at", "day"])
    return ck


def safe_name(text):
    """A file name every phone accepts: letters, numbers and dashes only."""
    import re
    return re.sub(r"[^A-Za-z0-9]+", "-", str(text)).strip("-") or "report"


def wa_url(phone, text):
    digits = gw.whatsapp_digits(phone)
    return f"https://wa.me/{digits}?text={quote(text)}" if digits else f"https://wa.me/?text={quote(text)}"


def _email_cb(supabase, gym_id, member, subject, text_key, button, on_done, args):
    import gympulse_campaigns as gcamp
    body = st.session_state.get(text_key) or ""
    ok, msg = gcamp.email_member(supabase, gym_id, member, subject, body, button)
    st.session_state["grow_flash" if ok else "grow_error"] = msg
    if ok and on_done:
        on_done(*args)
        st.session_state["grow_flash"] = msg


def send_row(text_key, member, key, subject, done_label=None, on_done=None, args=(),
             button=None, important=False, supabase=None, gym_id=None):
    """Email first (a branded letter from the gym), WhatsApp second. 'important'
    messages also suggest WhatsApp, because members see it within minutes."""
    m = dict(member)
    text = st.session_state.get(text_key) or ""
    has_email = "@" in gw._text(m.get("email"))
    cols = st.columns(3 if done_label else 2)
    cols[0].button("Send email", key=f"{key}_em", type="primary", icon=":material/mail:",
                   use_container_width=True, disabled=not has_email,
                   on_click=_email_cb, args=(supabase, gym_id, m, subject, text_key, button, on_done, args))
    cols[1].link_button("WhatsApp", wa_url(m.get("phone"), text), icon=":material/chat:",
                        use_container_width=True)
    if done_label and on_done:
        cols[2].button(done_label, key=key, on_click=on_done, args=args, use_container_width=True)
    if not has_email:
        st.caption("No email address on file, so use WhatsApp, or add their email on their profile.")
    elif important:
        st.caption("Important message: email it, and send it on WhatsApp too so they see it today.")


def _message_box(text, key, height=140):
    return st.text_area("Message", text, height=height, key=key, label_visibility="collapsed")


def _need_sql(rows):
    if rows is None:
        st.info(SQL_HINT)
        return True
    return False


def _save_settings(supabase, owner_id, patch, message):
    profile = st.session_state.get("user_profile") or {}
    s = {**dict(profile.get("settings") or {}), **patch}
    try:
        supabase.table("profiles").update({"settings": s}).eq("id", owner_id).execute()
        profile["settings"] = s
        st.session_state["user_profile"] = profile
        st.session_state["grow_flash"] = message
    except Exception as error:
        st.error(f"Could not save: {error}")


# ================================================================== 1. Collect renewals
def reference_for(member_id, name):
    return f"GP-{_first(name).upper()[:8]}-{str(member_id).replace('-', '')[:4].upper()}"


def plan_price(row):
    plan = gw.plan_name(row.get("membership_type"))
    return plan, float(row.get("monthly_fee") or 0) * gw.PLAN_MONTHS[plan]


def member_story(m, checkins):
    """What the member has already put in: real visits only."""
    mine = checkins[checkins["member_id"] == m["id"]] if len(checkins) else checkins
    days = mine.drop_duplicates("day") if len(mine) else mine
    since = pd.Timestamp(_today() - timedelta(days=30))
    return {"total": int(len(days)),
            "recent": int((days["at"] >= since).sum()) if len(days) else 0,
            "last": days["at"].max().date() if len(days) else None,
            "joined": m.get("joined") if m.get("joined") and not pd.isna(m.get("joined")) else None,
            "goal": gw._text(m.get("fitness_goal"))}


def _progress_line(story, biz):
    if story["total"] >= 3 and story["joined"]:
        line = f"You've trained at {biz} {story['total']} times since {story['joined']:%B}"
        line += f", {story['recent']} of them in the last 30 days." if story["recent"] else "."
        return line
    if story["last"]:
        return f"Your last session with us was on {story['last']:%A %d %B}."
    return ""


def renewal_email(name, amount, plan, end, pay, story, reminder=False):
    """(subject, body) for an email that invites the member in instead of chasing money.
    No bank details in email: members get those by replying, or on WhatsApp."""
    biz, owner = _biz()
    first = _first(name)
    days = (end - _today()).days if end else None
    lapsed = days is not None and days < 0
    if reminder:
        subject = f"{first}, we'd love to see you back this week"
    elif lapsed:
        subject = f"Your spot at {biz} is still here, {first}"
    else:
        subject = f"{first}, keep your momentum going at {biz}"
    para = [f"Hi {first},"]
    prog = _progress_line(story, biz)
    goal = gw._goal_phrase(story.get("goal"))
    if prog:
        para.append(prog + (f" Every session is a step{goal}, so let's keep it going." if goal else
                            " That consistency is what gets results, so let's keep it going."))
    if days is None:
        para.append(f"Your {gw.plan_phrase(plan)} membership is due for renewal ({_money(amount)}).")
    elif lapsed:
        para.append(f"Your {gw.plan_phrase(plan)} membership ended on {end:%d %B}, but your spot is still here and "
                    f"so is everything you've built. Renewal is {_money(amount)}.")
    elif days == 0:
        para.append(f"Your {gw.plan_phrase(plan)} membership renews today. Renewal is {_money(amount)}.")
    else:
        para.append(f"Your {gw.plan_phrase(plan)} membership renews on {end:%A %d %B}. Renewal is {_money(amount)}.")
    perk = gw._text(pay.get("perk"))
    para.append("The easiest way to renew is at the front desk on your next visit. It takes two minutes, "
                "and you can go straight into your session." + (f" Renew in person this week and you'll get {perk}." if perk else ""))
    para.append("Reply to this email with the day you're coming in, and we'll have everything ready for you.")
    if pay.get("paystack_link"):
        para.append("If you'd rather renew now, you can pay securely online with Paystack using the button below.")
    para.append(f"See you soon,\n{owner}\n{biz}".replace("\n\n", "\n"))
    return subject, "\n\n".join(para)


def renewal_buttons(pay):
    import gympulse_campaigns as gcamp
    b = gcamp.brand()
    come = gcamp.button_url("whatsapp", b) or (f"mailto:{b['company_email']}" if b.get("company_email") else "")
    out = []
    if come:
        out.append(("Tell us when you're coming", come))
    if pay.get("paystack_link"):
        out.append(("Pay securely with Paystack", pay["paystack_link"]))
    return out


def renewal_text(name, amount, plan, end, pay, ref, story=None, reminder=False):
    """The WhatsApp version: same invitation, with payment options at the end."""
    biz, owner = _biz()
    first = _first(name)
    story = story or {"total": 0, "recent": 0, "last": None, "joined": None, "goal": ""}
    days = (end - _today()).days if end else None
    when = ("is due for renewal" if days is None else "renews today" if days == 0 else
            f"renews on {end:%a %d %b}" if days > 0 else f"ended on {end:%d %b}, but your spot is still here")
    prog = _progress_line(story, biz)
    lines = [f"Hi {first}! 👋 " + ("Just checking in. " if reminder else "") + (prog + " 💪" if prog else "").strip(),
             f"\nYour {gw.plan_phrase(plan)} membership {when}. Renewal is {_money(amount)}."]
    perk = gw._text(pay.get("perk"))
    lines.append("\nCome in this week and renew at the front desk, it only takes two minutes"
                 + (f", and you'll get {perk}." if perk else ".") + " Which day works for you?")
    extra = []
    if pay.get("paystack_link"):
        extra.append(f"Pay online: {pay['paystack_link']}")
    if pay.get("bank_account"):
        extra.append(f"Or transfer: {pay.get('bank_name', '')} · {pay['bank_account']} · {pay.get('bank_holder', '')}"
                     f" (reference {ref})")
    if extra:
        lines.append("\nPrefer to pay now?\n" + "\n".join(extra) + "\nJust send the receipt here and I'll confirm it.")
    lines.append(f"\n{owner}")
    return "\n".join(l for l in lines if l.strip())


def _renewal_email_cb(supabase, gym_id, m, subj_key, body_key, buttons, on_done, args):
    import gympulse_campaigns as gcamp
    ok, msg = gcamp.email_member(supabase, gym_id, m, st.session_state.get(subj_key) or "",
                                 st.session_state.get(body_key) or "", buttons)
    st.session_state["grow_flash" if ok else "grow_error"] = msg
    if ok and on_done:
        on_done(*args)
        st.session_state["grow_flash"] = msg


def renewal_composer(supabase, gym_id, m, amount, plan, ref, pay, story, key, reminder=False, request=True):
    """Email (recommended) and WhatsApp versions of one renewal message."""
    m = dict(m)
    import zlib
    key = f"{key}_{zlib.crc32(repr(sorted(pay.items())).encode()) % 100000}"   # redraft when payment details change
    subject, body = renewal_email(m["full_name"], amount, plan, m.get("end"), pay, story, reminder)
    buttons = renewal_buttons(pay)
    t_email, t_wa = st.tabs(["Email (recommended)", "WhatsApp"])
    log = (supabase, gym_id, m["id"], amount, plan, ref)
    with t_email:
        has_email = "@" in gw._text(m.get("email"))
        st.text_input("Subject", subject, key=f"{key}_subj")
        st.text_area("Email", body, height=300, key=f"{key}_body", label_visibility="collapsed")
        st.caption("No bank details in emails: they look like scams in an inbox. The email invites the member in "
                   "to renew at the front desk" + (", with a secure Paystack button." if pay.get("paystack_link") else
                                                   ". Add a Paystack link above for a secure online option."))
        with st.expander("Preview the email"):
            import gympulse_campaigns as gcamp
            import streamlit.components.v1 as components
            components.html(gcamp.render_message(gcamp.brand(), st.session_state.get(f"{key}_subj") or subject,
                                                 st.session_state.get(f"{key}_body") or body, "#", buttons),
                            height=760, scrolling=True)
        st.button("Send email", key=f"{key}_send", type="primary", icon=":material/mail:", disabled=not has_email,
                  use_container_width=True, on_click=_renewal_email_cb,
                  args=(supabase, gym_id, m, f"{key}_subj", f"{key}_body", buttons,
                        _log_request if request else None, log + ("Email",) if request else ()))
        if not has_email:
            st.caption("No email address on file. Use WhatsApp, or add their email on their profile.")
    with t_wa:
        text = st.text_area("WhatsApp", renewal_text(m["full_name"], amount, plan, m.get("end"), pay, ref, story, reminder),
                            height=260, key=f"{key}_wa", label_visibility="collapsed")
        c1, c2 = st.columns(2)
        c1.link_button("Open in WhatsApp", wa_url(m.get("phone"), text), icon=":material/chat:", use_container_width=True)
        if request:
            c2.button("I sent it on WhatsApp", key=f"{key}_wasent", use_container_width=True,
                      on_click=_log_request, args=log + ("WhatsApp",))
        st.caption("WhatsApp from your gym's number is where bank details belong, at the end, as an option.")


def _mark_paid(supabase, gym_id, row, amount, plan, method, req_id=None):
    import gympulse_revenue as gr
    end = row.get("end") if _has_date(row.get("end")) else None
    today = _today()
    start = end if (end and end >= today) else today
    try:
        msg = gr.record_payment(supabase, gym_id, row["id"], gw._text(row.get("full_name"), "Member"),
                                float(amount), plan, start, method=method,
                                current_end=end, act=True, note=f"Ref {reference_for(row['id'], row.get('full_name'))}")
    except Exception as error:
        st.session_state["grow_flash"] = f"Could not record the payment: {error}"
        return
    if req_id:
        try:
            supabase.table("payment_requests").update(
                {"status": "paid", "paid_at": datetime.now(timezone.utc).isoformat(), "method": method}
            ).eq("id", req_id).execute()
        except Exception:
            pass
    gw.bump_data_version()
    st.session_state["grow_flash"] = msg


def _log_request(supabase, gym_id, mid, amount, plan, ref, channel="WhatsApp"):
    try:
        supabase.table("payment_requests").insert({
            "gym_id": gym_id, "member_id": mid, "amount": float(amount), "plan": plan,
            "reference": ref, "channel": channel, "status": "pending"}).execute()
        gw.bump_data_version()
        st.session_state["grow_flash"] = "Marked as requested. It's now in Waiting for payment."
    except Exception:
        st.session_state["grow_flash"] = SQL_HINT


def render_collect(supabase, gym_id, owner_id):
    s = _settings()
    pay = dict(s.get("collect") or {})
    with st.expander("Your payment details" + ("" if pay.get("bank_account") or pay.get("paystack_link")
                                              else " · set these up first"),
                     expanded=not (pay.get("bank_account") or pay.get("paystack_link"))):
        st.caption("Members pay you directly. GymPulse never touches the money. Bank details only go into "
                   "WhatsApp messages; emails invite members in and offer your Paystack link.")
        c1, c2, c3 = st.columns(3)
        bank = c1.text_input("Bank", pay.get("bank_name", ""), placeholder="e.g. GTBank")
        acct = c2.text_input("Account number", pay.get("bank_account", ""), placeholder="0123456789")
        holder = c3.text_input("Account name", pay.get("bank_holder", ""), placeholder="e.g. Nuelarch Fitness Ltd")
        link = st.text_input("Paystack payment page (optional)", pay.get("paystack_link", ""),
                             placeholder="e.g. https://paystack.com/pay/your-gym",
                             help="Create a payment page in your Paystack dashboard (Payments → Payment pages) and paste its link.")
        perk = st.text_input("Perk for renewing in person (optional)", pay.get("perk", ""),
                             placeholder="e.g. a free smoothie, or a free body-composition scan",
                             help="Only shown if you type one. GymPulse never invents offers.")
        if st.button("Save payment details", type="primary", key="grow_pay_save"):
            _save_settings(supabase, owner_id, {"collect": {"bank_name": bank.strip(), "bank_account": acct.strip(),
                                                           "bank_holder": holder.strip(), "paystack_link": link.strip(),
                                                           "perk": perk.strip()}},
                           "Payment details saved.")
            st.rerun()

    df = _members(supabase, gym_id)
    if df.empty:
        st.info("Add members first.")
        return
    reqs = _rows(supabase, "payment_requests", gym_id)
    pending = [r for r in (reqs or []) if r.get("status") == "pending"]
    pending_ids = {r["member_id"] for r in pending}
    ck = _checkins(supabase, gym_id, 400)
    today = _today()
    df = df[df["end"].notna()].copy()
    df["days_left"] = [(e - today).days for e in df["end"]]
    due = df[(df["days_left"] <= 14) & (df["days_left"] >= -30)].sort_values("days_left")

    gw.kpi_row([
        ("Due in 14 days", str(int((due["days_left"] >= 0).sum())), "cyan", "Renew before they lapse"),
        ("Lapsed (30 days)", str(int((due["days_left"] < 0).sum())), "red", "Still easy to win back"),
        ("Waiting for payment", str(len(pending)), "amber", "Asked, not yet paid"),
        ("Value due", _money(sum(plan_price(r)[1] for _, r in due.iterrows())), "lime", "From their current plans"),
    ])

    if pending:
        st.markdown('<div class="section-label">WAITING FOR PAYMENT</div>', unsafe_allow_html=True)
        by_id = {r["id"]: r for _, r in df.iterrows()}
        for r in pending:
            m = by_id.get(r["member_id"])
            if m is None:
                continue
            age = (datetime.now(timezone.utc) - pd.to_datetime(r["created_at"], utc=True, format="ISO8601")).days
            with st.container(border=True):
                gw._md(f'<b>{gw._esc(m["full_name"])}</b> · {_money(r["amount"])} · ref <code>{gw._esc(r["reference"])}</code> '
                       + gw.chip(f"asked {age} day{'s' if age != 1 else ''} ago", "amber" if age >= 3 else "grey"))
                c1, c2, c3 = st.columns(3)
                method = c1.selectbox("Paid by", ["Bank transfer", "Paystack", "Cash", "POS"], key=f"grow_pm_{r['id']}",
                                      label_visibility="collapsed")
                c2.button("Mark as paid", key=f"grow_paid_{r['id']}", type="primary", use_container_width=True,
                          on_click=_mark_paid, args=(supabase, gym_id, m, r["amount"], r.get("plan") or "Monthly", method, r["id"]))
                if c3.button("Cancel request", key=f"grow_rq_x_{r['id']}", use_container_width=True):
                    _update(supabase, "payment_requests", r["id"], {"status": "cancelled"})
                    st.rerun()
                if age >= 3:
                    with st.expander("Send a friendly follow-up"):
                        renewal_composer(supabase, gym_id, m, float(r["amount"]), r.get("plan") or "Monthly",
                                         r["reference"], pay, member_story(m, ck), f"grow_rem_{r['id']}",
                                         reminder=True, request=False)

    st.markdown('<div class="section-label">ASK FOR PAYMENT</div>', unsafe_allow_html=True)
    if due.empty:
        st.success("Nobody is due in the next 14 days. 🎉")
        return
    if not (pay.get("bank_account") or pay.get("paystack_link")):
        st.info("Tip: add your Paystack link above for a secure pay-online button, and your bank details "
                "for WhatsApp messages.")
    for _, m in due.iterrows():
        if m["id"] in pending_ids:
            continue
        plan, amount = plan_price(m)
        ref = reference_for(m["id"], m["full_name"])
        dl = int(m["days_left"])
        tone, label = (("red", f"lapsed {-dl}d") if dl < 0 else ("amber", "ends today") if dl == 0
                       else ("cyan", f"{dl} days left"))
        with st.expander(f"{m['full_name']} · {_money(amount)} · {label}"):
            gw._md(gw.chip(plan, "grey") + gw.chip(label, tone) + gw.chip(f"Ref {ref}", "lime"))
            c1, c2 = st.columns(2)
            amt = c1.number_input("Amount (₦)", min_value=0.0, value=float(amount), step=1000.0, key=f"grow_amt_{m['id']}")
            plans = gw.PLANS
            plan = c2.selectbox("Plan", plans, index=plans.index(plan), key=f"grow_plan_{m['id']}")
            renewal_composer(supabase, gym_id, m, amt, plan, ref, pay, member_story(m, ck),
                             f"grow_rn_{m['id']}_{amt:.0f}_{plan}")
            st.button("Already paid? Mark as paid", key=f"grow_pd_{m['id']}", use_container_width=True,
                      on_click=_mark_paid, args=(supabase, gym_id, m, amt, plan, "Bank transfer"))
            st.caption("Sending it moves them to Waiting for payment, where you mark it paid when they renew.")


# ================================================================== 2. First 90 days
ONBOARDING = [
    # step, title, day it becomes due, extra condition, message
    ("welcome", "Welcome", 0, None,
     "Hi {first}! 🎉 Welcome to {biz}. We're so glad you joined. Your first few visits are the most important, "
     "so if you need help with a plan or the equipment, just ask anyone in the team. See you soon! 💪\n{owner}"),
    ("visit3", "Third-visit check-in", 0, "visits3",
     "Hi {first}! Three sessions in at {biz}, that's how habits start 🔥 How are you finding it so far? "
     "Anything we can help with?\n{owner}"),
    ("trainer", "Meet a trainer", 14, None,
     "Hi {first}! Two weeks in 👏 I'd love you to meet {trainer}, one of our coaches. "
     "A quick chat with a coach makes a big difference{goal_part}. Want me to set it up?\n{owner}"),
    ("day30", "30-day progress check", 30, None,
     "Hi {first}! It's been a month since you joined {biz} 🎉 Let's do a quick progress check, "
     "weight, measurements or a personal best, so you can see how far you've come. When are you next in?\n{owner}"),
    ("day60", "60-day goal review", 60, None,
     "Hi {first}! Two months strong 💪 Let's take 15 minutes to review your plan{goal_part} and set your next target. "
     "Reply with a day that works for you.\n{owner}"),
    ("day90", "90 days, celebrate", 90, None,
     "Hi {first}! 🎊 90 days at {biz}! Most people quit before this point and you didn't. "
     "We're proud of you. Here's to the next 90!\n{owner}"),
]


ONBOARDING_SUBJECTS = {"welcome": "Welcome to {biz}", "visit3": "Three sessions in at {biz}",
                       "trainer": "Meet one of our coaches", "day30": "Your 30-day progress check",
                       "day60": "Let's review your goals", "day90": "90 days at {biz}"}


def onboarding_message(step_text, m, trainer_name):
    biz, owner = _biz()
    return step_text.format(first=_first(m.get("full_name")), biz=biz, owner=owner,
                            trainer=trainer_name or "one of our coaches",
                            goal_part=gw._goal_phrase(m.get("fitness_goal")))


def onboarding_plan(members, checkins, done_rows, today=None):
    """Every new member (joined in the last 90 days) with their visits and the next step due."""
    today = today or _today()
    done = {}
    for r in done_rows or []:
        done.setdefault(r["member_id"], set()).add(r["step"])
    visits = checkins.groupby("member_id").size().to_dict() if len(checkins) else {}
    out = []
    for _, m in members.iterrows():
        if m["joined"] is None or pd.isna(m["joined"]):
            continue
        age = (today - m["joined"]).days
        if age < 0 or age > 97:
            continue
        n = int(visits.get(m["id"], 0))
        steps = []
        for step, title, day, cond, text in ONBOARDING:
            is_due = age >= day and (cond != "visits3" or n >= 3)
            steps.append({"step": step, "title": title, "due": is_due, "done": step in done.get(m["id"], set()),
                          "text": text})
        due = [s for s in steps if s["due"]]
        latest = due[-1] if due else None
        for s in due[:-1]:
            s["skipped"] = not s["done"]
        nxt = latest if latest and not latest["done"] else None
        out.append({"m": m, "age": age, "visits": n, "steps": steps, "next": nxt,
                    "no_show": age >= 7 and n == 0, "quiet": age >= 14 and n <= 2})
    return sorted(out, key=lambda x: (not x["no_show"], x["next"] is None, -x["age"]))


def _step_done(supabase, gym_id, mid, step):
    try:
        supabase.table("onboarding_steps").insert({"gym_id": gym_id, "member_id": mid, "step": step}).execute()
        gw.bump_data_version()
        st.session_state["grow_flash"] = "Step marked done."
    except Exception as error:
        if not gw._is_duplicate_error(error):
            st.session_state["grow_flash"] = SQL_HINT


def render_onboarding(supabase, gym_id):
    st.caption("New members are the most likely to quit. Each person gets six touches in their first 90 days. "
               "Alerts flag anyone who hasn't come in during their first week.")
    done_rows = _rows(supabase, "onboarding_steps", gym_id)
    if _need_sql(done_rows):
        return
    df = _members(supabase, gym_id)
    ck = _checkins(supabase, gym_id, 100)
    plan = onboarding_plan(df, ck, done_rows)
    if not plan:
        st.info("No members joined in the last 90 days.")
        return
    trainers = gw.load_trainers(supabase, gym_id)
    gw.kpi_row([
        ("New members", str(len(plan)), "cyan", "Joined in the last 90 days"),
        ("No first-week visit", str(sum(p["no_show"] for p in plan)), "red", "Call them today"),
        ("Steps due", str(sum(p["next"] is not None for p in plan)), "amber", "Ready to send"),
        ("Made it to 90 days", str(sum(p["age"] >= 90 for p in plan)), "lime", "Still with you"),
    ])
    for p in plan:
        m = p["m"]
        chips = gw.chip(f"day {p['age']}", "grey") + gw.chip(f"{p['visits']} visit{'s' if p['visits'] != 1 else ''}", "cyan")
        if p["no_show"]:
            chips += gw.chip("no first-week visit", "red", dot=True)
        elif p["quiet"]:
            chips += gw.chip("quiet start", "amber", dot=True)
        progress = "".join("●" if s["done"] else "–" if s.get("skipped") else "○" for s in p["steps"])
        title = f"{m['full_name']} · {progress}" + (f" · next: {p['next']['title']}" if p["next"] else " · all caught up")
        with st.expander(title, expanded=p["no_show"]):
            gw._md(f'<div class="chip-row">{chips}</div>')
            if p["no_show"]:
                text = (f"Hi {_first(m['full_name'])}! It's {_biz()[1] or 'the team'} from {_biz()[0]} 👋 We haven't seen you yet "
                        "since you joined. Is there anything stopping you? I'd love to help you get started, even a "
                        "short first session counts. 💪")
                st.markdown("**First-week rescue**")
                _message_box(text, f"grow_ob_rescue_{m['id']}")
                send_row(f"grow_ob_rescue_{m['id']}", m, f"grow_obr_{m['id']}", f"We'd love to see you at {_biz()[0]}",
                         important=True, supabase=supabase, gym_id=gym_id)
            if p["next"]:
                t = gw.pick_trainer(trainers, m.get("fitness_goal"))
                st.markdown(f"**{p['next']['title']}**")
                k = f"grow_ob_{m['id']}_{p['next']['step']}"
                _message_box(onboarding_message(p["next"]["text"], m, gw._text((t or {}).get("full_name"))), k)
                send_row(k, m, f"grow_obd_{m['id']}_{p['next']['step']}", ONBOARDING_SUBJECTS[p["next"]["step"]].format(biz=_biz()[0]),
                         "Mark step done", _step_done, (supabase, gym_id, m["id"], p["next"]["step"]),
                         supabase=supabase, gym_id=gym_id)
            gw._md(" ".join(gw.chip(("✓ " if s["done"] else "") + s["title"],
                                    "lime" if s["done"] else "grey" if s.get("skipped") else "amber" if s["due"] else "grey")
                            for s in p["steps"]))
            if any(s.get("skipped") for s in p["steps"]):
                st.caption("Grey steps were due before this member reached the next one, so they're skipped.")


# ================================================================== 3. Freeze
FREEZE_REASONS = ["Travel", "December holidays", "Ramadan", "Exams", "Injury or health", "Work", "Other"]


def process_freezes(supabase, gym_id):
    """Start and end freezes whose dates have come. Safe to call on every visit."""
    rows = _rows(supabase, "member_freezes", gym_id, order="starts_on")
    if not rows:
        return 0
    today = _today()
    changed = 0
    for f in rows:
        start, end = date.fromisoformat(f["starts_on"]), date.fromisoformat(f["ends_on"])
        try:
            if f["status"] == "scheduled" and start <= today <= end:
                supabase.table("members").update({"suspended": True}).eq("id", f["member_id"]).execute()
                supabase.table("member_freezes").update({"status": "active"}).eq("id", f["id"]).execute()
                changed += 1
            elif f["status"] in ("scheduled", "active") and today > end:
                supabase.table("members").update({"suspended": False}).eq("id", f["member_id"]).execute()
                supabase.table("member_freezes").update({"status": "ended"}).eq("id", f["id"]).execute()
                changed += 1
        except Exception:
            pass
    if changed:
        gw.bump_data_version()
    return changed


def create_freeze(supabase, gym_id, m, start, end, reason, extend=True):
    row = {"gym_id": gym_id, "member_id": m["id"], "starts_on": start.isoformat(), "ends_on": end.isoformat(),
           "reason": reason, "status": "scheduled", "extended": bool(extend)}
    if not _insert(supabase, "member_freezes", row):
        return False
    if extend and _has_date(m.get("end")):
        days = (end - start).days + 1
        new_end = m["end"] + timedelta(days=days)
        try:
            supabase.table("members").update({"membership_end": new_end.isoformat()}).eq("id", m["id"]).execute()
        except Exception:
            pass
    process_freezes(supabase, gym_id)
    return True


def render_freeze(supabase, gym_id):
    st.caption("A paused member comes back. A cancelled one rarely does. Freeze a membership for travel, "
               "December, Ramadan, exams or injury, and their end date moves forward by the same number of days.")
    rows = _rows(supabase, "member_freezes", gym_id, order="starts_on")
    if _need_sql(rows):
        return
    process_freezes(supabase, gym_id)
    df = _members(supabase, gym_id)
    if df.empty:
        st.info("Add members first.")
        return
    names = _member_names(df)
    by_id = {r["id"]: r for _, r in df.iterrows()}
    today = _today()
    live = [f for f in rows if f["status"] in ("scheduled", "active")]
    ending = [f for f in live if 0 <= (date.fromisoformat(f["ends_on"]) - today).days <= 7]
    gw.kpi_row([("Frozen now", str(sum(f["status"] == "active" for f in live)), "cyan", "Paused, not lost"),
                ("Back within 7 days", str(len(ending)), "lime", "Send a welcome back"),
                ("Saved by freezing", str(len(rows)), "amber", "All-time freezes instead of cancelling")])

    with st.expander("Freeze a membership", expanded=not live):
        with st.form("grow_freeze"):
            ids = list(names)
            mid = st.selectbox("Member", ids, format_func=names.get)
            c1, c2, c3 = st.columns(3)
            start = c1.date_input("From", today)
            end = c2.date_input("Until", today + timedelta(days=30))
            reason = c3.selectbox("Reason", FREEZE_REASONS)
            extend = st.checkbox("Move their membership end date forward by the freeze length", value=True)
            ok = st.form_submit_button("Freeze membership", type="primary")
        if ok:
            if end < start:
                st.error("The end date must be after the start date.")
            elif (end - start).days > 92:
                st.error("Freezes can be up to 3 months.")
            elif create_freeze(supabase, gym_id, by_id[mid], start, end, reason, extend):
                st.session_state["grow_flash"] = f"{names[mid]} is frozen from {start:%d %b} to {end:%d %b}."
                st.rerun()

    biz, owner = _biz()
    for f in ending:
        m = by_id.get(f["member_id"])
        if m is None:
            continue
        with st.container(border=True):
            back = date.fromisoformat(f["ends_on"]) + timedelta(days=1)
            gw._md(f"<b>{gw._esc(names.get(f['member_id'], 'Member'))}</b> is back on {back:%A %d %b} "
                   + gw.chip(f["reason"] or "Freeze", "cyan"))
            _message_box(f"Hi {_first(m['full_name'])}! 👋 Your break ends soon. We can't wait to have you back at "
                         f"{biz} from {back:%A %d %B}. Want me to book you in for your first session back? 💪\n{owner}",
                         f"grow_fz_msg_{f['id']}")
            send_row(f"grow_fz_msg_{f['id']}", m, f"grow_fzs_{f['id']}", f"Welcome back to {biz}",
                     supabase=supabase, gym_id=gym_id)

    if live:
        st.markdown('<div class="section-label">FROZEN AND SCHEDULED</div>', unsafe_allow_html=True)
        for f in live:
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"**{names.get(f['member_id'], 'Member')}** · {date.fromisoformat(f['starts_on']):%d %b} → "
                        f"{date.fromisoformat(f['ends_on']):%d %b} · {f.get('reason') or ''} · _{f['status']}_")
            if c2.button("End now", key=f"grow_fz_end_{f['id']}", use_container_width=True):
                _update(supabase, "member_freezes", f["id"], {"status": "ended", "ends_on": today.isoformat()})
                try:
                    supabase.table("members").update({"suspended": False}).eq("id", f["member_id"]).execute()
                except Exception:
                    pass
                st.rerun()

    with st.expander("Message for a member who wants to cancel"):
        st.caption("Offer a freeze before you accept a cancellation.")
        st.code(f"I completely understand. Before you cancel, can I pause your membership instead? "
                f"You can freeze for up to 3 months for travel, December, Ramadan, exams or injury, "
                f"and you won't lose any of the days you've paid for. Then you pick up right where you left off. "
                f"Shall I set that up for you?\n{owner}", language=None)


# ================================================================== 4. Why they left
EXIT_REASONS = ["Price", "Time or schedule", "Not seeing results", "Moved or relocated", "Injury or health",
                "Staff or service", "Travel", "Other"]
EXIT_ADVICE = {
    "Price": "Offer a cheaper off-peak plan, a quarterly discount, or a freeze before they cancel.",
    "Time or schedule": "Add early-morning (5:30–7am) or late classes, and promote weekend sessions.",
    "Not seeing results": "Book a free progress check at day 30 and a goal review at day 60 for every member.",
    "Moved or relocated": "Not much to fix. Ask for a referral to someone near the gym instead.",
    "Injury or health": "Offer a freeze and a gentle return plan with a trainer.",
    "Staff or service": "Look at this closely: talk to the team and follow up personally with these members.",
    "Travel": "Offer freezes before trips, especially in December and over the summer.",
    "Other": "Read the notes. A quick personal call often reveals what to change.",
}


def exit_survey_text(name):
    biz, owner = _biz()
    options = "\n".join(f"{i}. {r}" for i, r in enumerate(EXIT_REASONS, 1))
    return (f"Hi {_first(name)}, it's {owner or 'the team'} from {biz}. We've missed you! 🙏 "
            f"Could you tell us the main reason you stopped coming? Just reply with a number:\n\n{options}\n\n"
            "Your answer helps us get better, and if there's anything we can fix for you, I'd love to.")


def _reply_reason(supabase, gym_id, member_id):
    """If the member replied to the survey with a number, the reason it stands for."""
    try:
        rows = (supabase.table("messages").select("body, direction, created_at").eq("gym_id", gym_id)
                .eq("member_id", member_id).eq("direction", "in").order("created_at", desc=True)
                .limit(3).execute().data or [])
    except Exception:
        return None
    for r in rows:
        body = gw._text(r.get("body")).strip()
        if body[:1].isdigit():
            n = int(body[:1])
            if 1 <= n <= len(EXIT_REASONS):
                return EXIT_REASONS[n - 1]
    return None


def render_exit(supabase, gym_id):
    st.caption("Ask lapsed members one question on WhatsApp, record their answer, and see what's really "
               "driving people away.")
    rows = _rows(supabase, "exit_reasons", gym_id)
    if _need_sql(rows):
        return
    df = _members(supabase, gym_id)
    today = _today()
    asked = {r["member_id"] for r in rows}
    lapsed = df[df["end"].notna()].copy() if len(df) else df
    if len(lapsed):
        lapsed["gone"] = [(today - e).days for e in lapsed["end"]]
        lapsed = lapsed[(lapsed["gone"] > 0) & (lapsed["gone"] <= 120) & (~lapsed["id"].isin(asked))]

    recent = [r for r in rows if pd.to_datetime(r["created_at"], utc=True, format="ISO8601")
              >= pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=365)]
    if recent:
        counts = pd.Series([r["reason"] for r in recent]).value_counts()
        top, share = counts.index[0], counts.iloc[0] / counts.sum()
        gw._md(f'<div class="cc-brief"><b>{share:.0%} of members who left gave "{gw._esc(top)}" as the reason.</b> '
               f'{gw._esc(EXIT_ADVICE.get(top, ""))}</div>')
        chart = pd.DataFrame({"Reason": counts.index, "Members": counts.values}).set_index("Reason")
        st.bar_chart(chart, horizontal=True, color="#B7F34A", height=260)
    else:
        st.info("No reasons recorded yet. Send the survey to a lapsed member below to start.")

    st.markdown('<div class="section-label">ASK LAPSED MEMBERS</div>', unsafe_allow_html=True)
    if not len(lapsed):
        st.success("Everyone who lapsed in the last 120 days already has a reason recorded.")
    for _, m in (lapsed.sort_values("gone").iterrows() if len(lapsed) else []):
        guess = _reply_reason(supabase, gym_id, m["id"])
        with st.expander(f"{m['full_name']} · lapsed {m['gone']} day{'s' if m['gone'] != 1 else ''} ago" + (f" · replied: {guess}" if guess else "")):
            _message_box(exit_survey_text(m["full_name"]), f"grow_ex_msg_{m['id']}", 230)
            send_row(f"grow_ex_msg_{m['id']}", m, f"grow_exs_{m['id']}", f"We've missed you at {_biz()[0]}",
                     supabase=supabase, gym_id=gym_id)
            with st.form(f"grow_ex_{m['id']}"):
                c1, c2 = st.columns([1, 2])
                reason = c1.selectbox("Their reason", EXIT_REASONS,
                                      index=EXIT_REASONS.index(guess) if guess in EXIT_REASONS else 0)
                note = c2.text_input("Note (optional)", placeholder="e.g. moved to Ajah, new job hours")
                if st.form_submit_button("Save reason", type="primary"):
                    if _insert(supabase, "exit_reasons", {"gym_id": gym_id, "member_id": m["id"], "reason": reason,
                                                          "note": note.strip() or None,
                                                          "source": "whatsapp reply" if guess else "owner"}):
                        st.session_state["grow_flash"] = f"Saved: {m['full_name']} left because of {reason.lower()}."
                        st.rerun()
    if rows:
        with st.expander("All recorded reasons"):
            names = _member_names(df)
            st.dataframe(pd.DataFrame([{"Member": names.get(r["member_id"], "Former member"), "Reason": r["reason"],
                                        "Note": r.get("note") or "", "When": str(r["created_at"])[:10]} for r in rows]),
                         hide_index=True, use_container_width=True)


# ================================================================== 5. Progress
def progress_summary(logs, goal=""):
    """First vs latest weigh-in plus personal bests, for one member's logs (sorted oldest first)."""
    out = {"weight_change": None, "since": None, "pbs": {}}
    weights = [(r["logged_on"], float(r["weight_kg"])) for r in logs if r.get("weight_kg") not in (None, "")]
    if len(weights) >= 2:
        out["weight_change"] = round(weights[-1][1] - weights[0][1], 1)
        out["since"] = weights[0][0]
    for r in logs:
        if r.get("pb_name") and r.get("pb_value") not in (None, ""):
            name = gw._text(r["pb_name"]).strip().title()
            out["pbs"].setdefault(name, []).append((r["logged_on"], float(r["pb_value"])))
    return out


def _wants_loss(goal):
    g = gw._text(goal).lower()
    return any(w in g for w in ("loss", "lose", "fat", "slim", "tone", "weight"))


def shoutout(name, goal, summary):
    """A celebration message, only when the numbers show real progress in the right direction."""
    biz, owner = _biz()
    first = _first(name)
    wc = summary["weight_change"]
    if wc is not None and summary["since"]:
        since = date.fromisoformat(str(summary["since"])[:10])
        if _wants_loss(goal) and wc <= -2:
            return (f"Hi {first}! 🔥 You're down {abs(wc):g}kg since {since:%B}. That's real, consistent work. "
                    f"Everyone at {biz} is proud of you. Keep going! 💪\n{owner}")
        if not _wants_loss(goal) and wc >= 2:
            return (f"Hi {first}! 💪 You've gained {wc:g}kg since {since:%B}. Your hard work is showing. "
                    f"Proud of you from all of us at {biz}!\n{owner}")
    for pb, vals in summary["pbs"].items():
        if len(vals) >= 2 and vals[-1][1] > vals[0][1]:
            return (f"Hi {first}! 🏆 New personal best: {pb} {vals[-1][1]:g} (up from {vals[0][1]:g}). "
                    f"Amazing progress, keep it up!\n{owner}")
    return None


def render_progress(supabase, gym_id):
    st.caption("Members who can see their results stay. Log a weigh-in, measurement or personal best in "
               "10 seconds, and GymPulse drafts a shout-out when the numbers show real progress.")
    logs = _rows(supabase, "progress_logs", gym_id, order="logged_on", desc=False)
    if _need_sql(logs):
        return
    df = _members(supabase, gym_id)
    if df.empty:
        st.info("Add members first.")
        return
    names = _member_names(df)
    by_id = {r["id"]: r for _, r in df.iterrows()}
    import gympulse_automation as ga
    staff = ["Owner"] + ga.staff_list() + [gw._text(t.get("full_name")) for t in gw.load_trainers(supabase, gym_id)]
    with st.form("grow_prog", clear_on_submit=True):
        c1, c2 = st.columns([2, 1])
        mid = c1.selectbox("Member", list(names), format_func=names.get)
        day = c2.date_input("Date", _today())
        c3, c4, c5 = st.columns(3)
        w = c3.number_input("Weight (kg)", min_value=0.0, max_value=400.0, value=0.0, step=0.1)
        waist = c4.number_input("Waist (cm)", min_value=0.0, max_value=300.0, value=0.0, step=0.5)
        bf = c5.number_input("Body fat %", min_value=0.0, max_value=80.0, value=0.0, step=0.1)
        c6, c7, c8 = st.columns(3)
        pb = c6.text_input("Personal best (optional)", placeholder="e.g. Squat")
        pbv = c7.number_input("PB value", min_value=0.0, value=0.0, step=0.5, help="kg, reps or minutes")
        who = c8.selectbox("Logged by", list(dict.fromkeys(s for s in staff if s)))
        note = st.text_input("Note (optional)")
        ok = st.form_submit_button("Save progress", type="primary")
    if ok:
        row = {"gym_id": gym_id, "member_id": mid, "logged_on": day.isoformat(),
               "weight_kg": w or None, "waist_cm": waist or None, "body_fat": bf or None,
               "pb_name": pb.strip() or None, "pb_value": pbv if pb.strip() and pbv else None,
               "note": note.strip() or None, "logged_by": who}
        if not any(row[k] for k in ("weight_kg", "waist_cm", "body_fat", "pb_value", "note")):
            st.error("Enter at least one number or a note.")
        elif _insert(supabase, "progress_logs", row):
            st.session_state["grow_flash"] = f"Progress saved for {names[mid]}."
            st.rerun()

    per = {}
    for r in logs:
        per.setdefault(r["member_id"], []).append(r)
    wins = []
    for mid, rows in per.items():
        m = by_id.get(mid)
        if m is None:
            continue
        text = shoutout(m["full_name"], m.get("fitness_goal"), progress_summary(rows, m.get("fitness_goal")))
        if text:
            wins.append((m, text))
    if wins:
        st.markdown('<div class="section-label">READY TO CELEBRATE</div>', unsafe_allow_html=True)
        for m, text in wins:
            with st.expander(f"🎉 {m['full_name']}"):
                _message_box(text, f"grow_pg_sh_{m['id']}")
                send_row(f"grow_pg_sh_{m['id']}", m, f"grow_pgs_{m['id']}", "Look at your progress",
                         supabase=supabase, gym_id=gym_id)
    if per:
        st.markdown('<div class="section-label">TRACKED MEMBERS</div>', unsafe_allow_html=True)
        table = []
        for mid, rows in per.items():
            sm = progress_summary(rows)
            table.append({"Member": names.get(mid, "Member"), "Entries": len(rows),
                          "Weight change (kg)": sm["weight_change"],
                          "Latest": str(rows[-1]["logged_on"])[:10],
                          "Personal bests": ", ".join(f"{k} {v[-1][1]:g}" for k, v in sm["pbs"].items())})
        st.dataframe(pd.DataFrame(table), hide_index=True, use_container_width=True)
        pick = st.selectbox("See one member's history", list(per), format_func=lambda i: names.get(i, "Member"),
                            key="grow_pg_pick")
        hist = pd.DataFrame(per[pick])
        if "weight_kg" in hist and hist["weight_kg"].notna().sum() >= 2:
            chart = hist.dropna(subset=["weight_kg"]).assign(
                Date=lambda d: pd.to_datetime(d["logged_on"]), Weight=lambda d: d["weight_kg"].astype(float))
            import altair as alt
            lo, hi = chart["Weight"].min(), chart["Weight"].max()
            st.altair_chart(alt.Chart(chart).mark_line(point=alt.OverlayMarkDef(color="#22D3EE", size=60), color="#22D3EE").encode(
                x=alt.X("Date:T", title=None),
                y=alt.Y("Weight:Q", title="Weight (kg)", scale=alt.Scale(domain=[lo - 2, hi + 2]))
            ).properties(height=220), use_container_width=True)
        st.dataframe(hist[[c for c in ("logged_on", "weight_kg", "waist_cm", "body_fat", "pb_name", "pb_value",
                                       "note", "logged_by") if c in hist]].rename(columns={
            "logged_on": "Date", "weight_kg": "Weight", "waist_cm": "Waist", "body_fat": "Body fat %",
            "pb_name": "PB", "pb_value": "PB value", "note": "Note", "logged_by": "By"}),
            hide_index=True, use_container_width=True)


# ================================================================== 6. Referrals
REF_STAGES = ["invited", "visited", "joined", "rewarded"]


def render_referrals(supabase, gym_id, owner_id):
    st.caption("Members bring friends, friends join, and the member gets a real reward. Track every invite "
               "from first message to reward.")
    rows = _rows(supabase, "referrals", gym_id)
    if _need_sql(rows):
        return
    df = _members(supabase, gym_id)
    if df.empty:
        st.info("Add members first.")
        return
    names = _member_names(df)
    by_id = {r["id"]: r for _, r in df.iterrows()}
    s = _settings()
    reward_default = s.get("referral_reward") or "1 free week"
    c1, c2 = st.columns([3, 1])
    reward = c1.text_input("Reward for the member when their friend joins", reward_default, key="grow_ref_rw")
    if reward != reward_default and c2.button("Save reward", key="grow_ref_rw_save", use_container_width=True):
        _save_settings(supabase, owner_id, {"referral_reward": reward.strip()}, "Referral reward saved.")
        st.rerun()

    joined = [r for r in rows if r["status"] in ("joined", "rewarded")]
    gw.kpi_row([("Invites", str(len(rows)), "cyan", "Friends invited"),
                ("Joined", str(len(joined)), "lime", "Became members"),
                ("Rewards owed", str(sum(r["status"] == "joined" for r in rows)), "amber", "Give these out"),
                ("Conversion", f"{len(joined) / len(rows):.0%}" if rows else "–", "grey", "Invites that joined")])

    biz, owner = _biz()
    with st.expander("Ask a member to bring a friend"):
        mid = st.selectbox("Member", list(names), format_func=names.get, key="grow_ref_ask")
        m = by_id[mid]
        text = _message_box(f"Hi {_first(m['full_name'])}! 🙌 Training is better with a friend. Bring someone to {biz} this "
                            f"week and when they join, you get {reward}. Just reply with their name and number, "
                            f"and I'll sort out the rest. 💪\n{owner}", f"grow_ref_ask_msg_{mid}")
        send_row(f"grow_ref_ask_msg_{mid}", m, f"grow_refa_{mid}", f"Bring a friend to {biz}",
                 supabase=supabase, gym_id=gym_id)

    with st.form("grow_ref_new", clear_on_submit=True):
        st.markdown("**Record a referral**")
        c1, c2, c3 = st.columns(3)
        rid = c1.selectbox("Referred by", list(names), format_func=names.get)
        fname = c2.text_input("Friend's name")
        fphone = c3.text_input("Friend's phone")
        if st.form_submit_button("Add referral", type="primary"):
            if not fname.strip():
                st.error("Enter the friend's name.")
            elif _insert(supabase, "referrals", {"gym_id": gym_id, "referrer_id": rid, "friend_name": fname.strip(),
                                                 "friend_phone": fphone.strip() or None, "reward": reward}):
                st.session_state["grow_flash"] = f"Referral added: {fname.strip()}, invited by {names[rid]}."
                st.rerun()

    phones = {gw.whatsapp_digits(r.get("phone")): r["id"] for _, r in df.iterrows() if gw.whatsapp_digits(r.get("phone"))}
    for r in rows:
        if r["status"] == "rewarded":
            continue
        ref_name = names.get(r["referrer_id"], "A member")
        match = phones.get(gw.whatsapp_digits(r.get("friend_phone"))) if r.get("friend_phone") else None
        with st.container(border=True):
            gw._md(f"<b>{gw._esc(r['friend_name'])}</b> · invited by {gw._esc(ref_name)} "
                   + gw.chip(r["status"], {"invited": "grey", "visited": "cyan", "joined": "amber"}[r["status"]])
                   + (gw.chip("now a member", "lime") if match and r["status"] in ("invited", "visited") else ""))
            c1, c2, c3 = st.columns(3)
            if r["status"] == "invited":
                if c1.button("Visited", key=f"grow_rf_v_{r['id']}", use_container_width=True):
                    _update(supabase, "referrals", r["id"], {"status": "visited"}); st.rerun()
                if r.get("friend_phone"):
                    c3.link_button("Invite them", wa_url(r["friend_phone"],
                                   f"Hi {_first(r['friend_name'])}! {ref_name} said you'd love to train with them at {biz}. "
                                   f"Come in for a free session this week, when works for you? 💪\n{owner}"),
                                   use_container_width=True)
            if r["status"] in ("invited", "visited"):
                if c2.button("Joined", key=f"grow_rf_j_{r['id']}", type="primary", use_container_width=True):
                    _update(supabase, "referrals", r["id"], {"status": "joined", "joined_on": _today().isoformat(),
                                                            "friend_member_id": match}); st.rerun()
            if r["status"] == "joined":
                referrer = by_id.get(r["referrer_id"])
                if referrer is not None:
                    k = f"grow_rw_msg_{r['id']}"
                    st.session_state.setdefault(k, f"Hi {_first(referrer['full_name'])}! 🎁 {r['friend_name']} just joined "
                                                   f"{biz} thanks to you. Your reward: {r.get('reward') or reward}. "
                                                   f"Thank you! 🙏\n{owner}")
                    with c1.popover("Tell them their reward", use_container_width=True):
                        st.text_area("Message", key=k, height=140, label_visibility="collapsed")
                        send_row(k, referrer, f"grow_rws_{r['id']}", "Your referral reward",
                                 supabase=supabase, gym_id=gym_id)
                if c2.button("Reward given", key=f"grow_rf_r_{r['id']}", type="primary", use_container_width=True):
                    _update(supabase, "referrals", r["id"], {"status": "rewarded",
                                                            "rewarded_at": datetime.now(timezone.utc).isoformat()}); st.rerun()
    if joined:
        board = pd.Series([names.get(r["referrer_id"], "Former member") for r in joined]).value_counts()
        st.markdown('<div class="section-label">TOP REFERRERS</div>', unsafe_allow_html=True)
        for i, (n, c) in enumerate(board.head(5).items(), 1):
            st.markdown(f"{['🥇', '🥈', '🥉'][i - 1] if i <= 3 else f'{i}.'} **{n}** · {c} friend{'s' if c != 1 else ''} joined")


# ================================================================== 7. Challenges
def leaderboard(challenge, entries, checkins):
    start = pd.Timestamp(challenge["starts_on"])
    end = pd.Timestamp(challenge["ends_on"]) + pd.Timedelta(days=1)
    ids = [e["member_id"] for e in entries if e["challenge_id"] == challenge["id"]]
    if not ids:
        return pd.DataFrame(columns=["member_id", "visits"])
    ck = checkins[(checkins["at"] >= start) & (checkins["at"] < end) & (checkins["member_id"].isin(ids))] \
        if len(checkins) else checkins
    days = ck.drop_duplicates(["member_id", "day"]).groupby("member_id").size() if len(ck) else pd.Series(dtype=int)
    board = pd.DataFrame({"member_id": ids})
    board["visits"] = board["member_id"].map(days).fillna(0).astype(int)
    return board.sort_values("visits", ascending=False).reset_index(drop=True)


def render_challenges(supabase, gym_id):
    st.caption("Run a visits challenge. Members join, every real check-in counts (one per day), and the "
               "leaderboard updates by itself.")
    chals = _rows(supabase, "challenges", gym_id, order="starts_on")
    entries = _rows(supabase, "challenge_entries", gym_id)
    if _need_sql(chals) or _need_sql(entries):
        return
    df = _members(supabase, gym_id)
    names = _member_names(df)
    by_id = {r["id"]: r for _, r in df.iterrows()} if len(df) else {}
    today = _today()
    biz, owner = _biz()
    with st.expander("Start a challenge", expanded=not chals):
        with st.form("grow_ch_new"):
            name = st.text_input("Name", placeholder="e.g. 30-Day Consistency Challenge")
            c1, c2, c3 = st.columns(3)
            start = c1.date_input("Starts", today)
            end = c2.date_input("Ends", today + timedelta(days=30))
            target = c3.number_input("Target visits", 1, 100, 12)
            reward = st.text_input("Reward (optional)", placeholder="e.g. Free month for the top 3")
            if st.form_submit_button("Create challenge", type="primary"):
                if not name.strip() or end < start:
                    st.error("Give it a name and an end date after the start.")
                elif _insert(supabase, "challenges", {"gym_id": gym_id, "name": name.strip(), "starts_on": start.isoformat(),
                                                      "ends_on": end.isoformat(), "target_visits": int(target),
                                                      "reward": reward.strip() or None}):
                    st.session_state["grow_flash"] = f"{name.strip()} created. Now add members."
                    st.rerun()
    if not chals:
        return
    span = max((today - date.fromisoformat(min(c["starts_on"] for c in chals))).days + 2, 30)
    ck = _checkins(supabase, gym_id, min(span, 400))
    live = sorted(chals, key=lambda c: (date.fromisoformat(c["ends_on"]) < today, c["starts_on"]))
    pick = st.selectbox("Challenge", [c["id"] for c in live],
                        format_func=lambda i: next(f"{c['name']} ({date.fromisoformat(c['starts_on']):%d %b} → "
                                                   f"{date.fromisoformat(c['ends_on']):%d %b})" for c in chals if c["id"] == i),
                        key="grow_ch_pick")
    c = next(x for x in chals if x["id"] == pick)
    in_ids = {e["member_id"] for e in entries if e["challenge_id"] == pick}
    board = leaderboard(c, entries, ck)
    ended = date.fromisoformat(c["ends_on"]) < today
    gw.kpi_row([("Taking part", str(len(in_ids)), "cyan", ""),
                ("Hit the target", str(int((board["visits"] >= c["target_visits"]).sum())) if len(board) else "0", "lime", ""),
                ("Days left", "Finished" if ended else str((date.fromisoformat(c["ends_on"]) - today).days), "amber", ""),
                ("Target", str(c["target_visits"]), "grey", "visits to finish")])
    if c.get("reward"):
        st.caption(f"🎁 Reward: {c['reward']}")
    add = st.multiselect("Add members", [i for i in names if i not in in_ids], format_func=names.get, key=f"grow_ch_add_{pick}")
    if add and st.button(f"Add {len(add)} member{'s' if len(add) != 1 else ''}", type="primary", key=f"grow_ch_addb_{pick}"):
        try:
            supabase.table("challenge_entries").insert([{"gym_id": gym_id, "challenge_id": pick, "member_id": i}
                                                        for i in add]).execute()
            gw.bump_data_version()
            st.rerun()
        except Exception as error:
            st.error(f"Could not add: {error}")
    if len(board):
        lines, plain = [], []
        for i, r in board.iterrows():
            n = names.get(r["member_id"], "Member")
            pct = min(100, round(r["visits"] / max(c["target_visits"], 1) * 100))
            medal = ["🥇", "🥈", "🥉"][i] if i < 3 and r["visits"] else f"{i + 1}."
            gw._md(f'<div style="display:flex;align-items:center;gap:12px;margin:6px 0"><div style="width:34px">{medal}</div>'
                   f'<div style="flex:1"><b>{gw._esc(n)}</b> · {r["visits"]}/{c["target_visits"]} visits'
                   f'<div class="pbar" style="margin-top:4px"><span style="width:{pct}%;--tone:#B7F34A"></span></div></div></div>')
            lines.append(f"{medal} {n.split()[0]} · {r['visits']} visits")
            plain.append(f"{i + 1}. {n.split()[0]}: {r['visits']} visit{'s' if r['visits'] != 1 else ''}")
        top = "\n".join(lines[:10])
        text = _message_box(f"🏆 {c['name']} leaderboard at {biz}\n\n{top}\n\n"
                            + ("Congratulations to our winners! 🎉" if ended else
                               f"{(date.fromisoformat(c['ends_on']) - today).days} days to go. Every visit counts! 💪"),
                            f"grow_ch_share_{pick}", 230)
        c1, c2 = st.columns(2)
        if c1.button(f"Email everyone taking part ({len(board)})", key=f"grow_ch_em_{pick}", type="primary",
                     icon=":material/mail:", use_container_width=True):
            import gympulse_campaigns as gcamp
            sent = skipped = 0
            for mid in board["member_id"]:
                m = by_id.get(mid)
                if m is None:
                    skipped += 1
                    continue
                mine = next((i + 1 for i, x in enumerate(board["member_id"]) if x == mid), None)
                left = (date.fromisoformat(c["ends_on"]) - today).days
                letter = (f"Hi {_first(m['full_name'])},\n\nHere is the latest leaderboard for the {c['name']} at {biz}. "
                          f"You're in position {mine} of {len(board)}.\n\n" + "\n".join(plain[:10]) + "\n\n"
                          + ("Congratulations to our winners, and thank you for taking part."
                             if ended else f"{left} days to go. Every visit counts.")
                          + (f"\n\nReward: {c['reward']}" if c.get("reward") else "") + f"\n\n{owner}\n{biz}")
                ok, _ = gcamp.email_member(supabase, gym_id, dict(m), f"{c['name']}: the leaderboard", letter)
                sent += ok
                skipped += not ok
            st.success(f"Emailed {sent} member{'s' if sent != 1 else ''}."
                       + (f" {skipped} skipped (no email or unsubscribed)." if skipped else ""))
        c2.link_button("Share on WhatsApp", wa_url("", text), icon=":material/chat:", use_container_width=True)
        st.caption("Tip: paste the WhatsApp version into your members' group.")
    else:
        st.info("Add members to start the leaderboard.")


# ================================================================== 8. Corporate
def company_report(company, staff, checkins, today=None):
    today = today or _today()
    since = pd.Timestamp(today - timedelta(days=30))
    ids = list(staff["id"]) if len(staff) else []
    ck = checkins[(checkins["at"] >= since) & checkins["member_id"].isin(ids)] if len(checkins) and ids else checkins.iloc[0:0]
    visits = ck.drop_duplicates(["member_id", "day"]).groupby("member_id").size() if len(ck) else pd.Series(dtype=int)
    people = []
    for _, m in staff.iterrows():
        people.append({"name": gw._text(m["full_name"]), "visits": int(visits.get(m["id"], 0))})
    people.sort(key=lambda p: -p["visits"])
    active = sum(p["visits"] > 0 for p in people)
    return {"company": company, "enrolled": len(people), "active": active,
            "active_rate": active / len(people) if people else 0,
            "visits": sum(p["visits"] for p in people),
            "avg": (sum(p["visits"] for p in people) / len(people)) if people else 0, "people": people}


def company_pdf(rep):
    import gympulse_reports as rp
    biz, _ = _biz()
    c = rep["company"]
    rows = [[p["name"], str(p["visits"]), "Active" if p["visits"] else "Not seen"] for p in rep["people"]]
    blocks = [("kpis", [("Enrolled", str(rep["enrolled"]), "staff on the plan"),
                        ("Active", f"{rep['active_rate']:.0%}", f"{rep['active']} trained this month"),
                        ("Visits", str(rep["visits"]), "last 30 days"),
                        ("Average", f"{rep['avg']:.1f}", "visits per person")]),
              ("h", "Attendance by person"), ("table", ["Name", "Visits (30 days)", "Status"], rows),
              ("note", f"Attendance comes from real check-ins at {biz}. One visit per person per day.")]
    return rp.build_pdf(f"{c['name']} · Team attendance", f"Last 30 days to {_today():%d %B %Y}", blocks)


def render_corporate(supabase, gym_id):
    st.caption("Sell team memberships to companies, then send HR a monthly attendance report. "
               "Companies renew when they can see their staff using it.")
    comps = _rows(supabase, "companies", gym_id, order="name", desc=False)
    if _need_sql(comps):
        return
    df = _members(supabase, gym_id)
    names = _member_names(df)
    try:
        links = {r["id"]: r.get("company_id") for r in
                 (supabase.table("members").select("id, company_id").eq("gym_id", gym_id).execute().data or [])}
    except Exception:
        st.info(SQL_HINT)
        return
    with st.expander("Add a company", expanded=not comps):
        with st.form("grow_co_new", clear_on_submit=True):
            c1, c2 = st.columns(2)
            name = c1.text_input("Company name", placeholder="e.g. Lekki Tech Ltd")
            seats = c2.number_input("Seats on the plan", 0, 5000, 10)
            c3, c4, c5 = st.columns(3)
            hr = c3.text_input("HR contact name")
            hr_email = c4.text_input("HR email")
            hr_phone = c5.text_input("HR phone")
            fee = st.number_input("Monthly fee for the company (₦)", 0.0, step=10000.0)
            if st.form_submit_button("Add company", type="primary"):
                if not name.strip():
                    st.error("Enter the company name.")
                elif _insert(supabase, "companies", {"gym_id": gym_id, "name": name.strip(), "seats": int(seats) or None,
                                                     "hr_name": hr.strip() or None, "hr_email": hr_email.strip() or None,
                                                     "hr_phone": hr_phone.strip() or None, "monthly_fee": fee or None}):
                    st.session_state["grow_flash"] = f"{name.strip()} added. Now link their staff."
                    st.rerun()
    if not comps:
        return
    ck = _checkins(supabase, gym_id, 35)
    for c in comps:
        staff = df[df["id"].map(lambda i: links.get(i) == c["id"])] if len(df) else df
        rep = company_report(c, staff, ck)
        with st.expander(f"{c['name']} · {rep['enrolled']} staff · {rep['active_rate']:.0%} active this month"):
            gw.kpi_row([("Enrolled", f"{rep['enrolled']}" + (f"/{c['seats']}" if c.get("seats") else ""), "cyan", ""),
                        ("Active (30 days)", f"{rep['active_rate']:.0%}", "lime", f"{rep['active']} people"),
                        ("Visits", str(rep["visits"]), "amber", "last 30 days"),
                        ("Value", _money(c.get("monthly_fee") or 0), "grey", "per month")])
            current = [i for i in names if links.get(i) == c["id"]]
            chosen = st.multiselect("Staff on this plan", list(names), default=current, format_func=names.get,
                                    key=f"grow_co_staff_{c['id']}")
            if set(chosen) != set(current) and st.button("Save staff list", key=f"grow_co_save_{c['id']}", type="primary"):
                try:
                    for i in set(chosen) - set(current):
                        supabase.table("members").update({"company_id": c["id"]}).eq("id", i).execute()
                    for i in set(current) - set(chosen):
                        supabase.table("members").update({"company_id": None}).eq("id", i).execute()
                    gw.bump_data_version()
                    st.session_state["grow_flash"] = f"{c['name']} staff list saved."
                    st.rerun()
                except Exception as error:
                    st.error(f"Could not save: {error}")
            if rep["people"]:
                st.dataframe(pd.DataFrame([{"Name": p["name"], "Visits (30 days)": p["visits"],
                                            "Status": "Active" if p["visits"] else "Not seen"} for p in rep["people"]]),
                             hide_index=True, use_container_width=True)
            else:
                st.caption("No staff linked yet. Add them above. The report will show them once they're linked.")
            import gympulse_reports as rp
            biz, owner = _biz()
            fname = f"{safe_name(c['name'])}-attendance-{_today():%Y-%m}.pdf"
            try:
                pdf = company_pdf(rep)
            except Exception as error:
                pdf = None
                st.error(f"Could not build the PDF: {error}")
            summary = (f"Dear {gw._text(c.get('hr_name'), 'HR team')},\n\nPlease find attached {c['name']}'s gym "
                       f"attendance report from {biz} for the last 30 days.\n\n{rep['active']} of {rep['enrolled']} "
                       f"enrolled staff trained ({rep['active_rate']:.0%}), with {rep['visits']} visits in total.\n\n"
                       f"We'd be glad to help the rest of the team get started.\n\nKind regards,\n{owner}\n{biz}")
            c1, c2, c3 = st.columns(3)
            if pdf:
                with c1:
                    rp.download_link("Download HR report (PDF)", pdf, fname, rp.PDF, f"grow_co_pdf_{c['id']}")
            import gympulse_campaigns as gcamp
            if c.get("hr_email") and pdf and gcamp.ready():
                if c2.button("Email the report to HR", key=f"grow_co_em_{c['id']}", type="primary",
                             icon=":material/mail:", use_container_width=True):
                    try:
                        gcamp.email_letter(c["hr_email"], f"{c['name']}: gym attendance report, {_today():%B %Y}",
                                           summary, attachments=[(fname, pdf)])
                        st.success(f"Report emailed to {c['hr_email']} with the PDF attached.")
                    except Exception as error:
                        st.error(f"Could not send: {error}")
            elif not c.get("hr_email"):
                c2.caption("Add an HR email to send the report with the PDF attached.")
            if c.get("hr_phone"):
                c3.link_button("WhatsApp summary", wa_url(c["hr_phone"], summary.replace("Please find attached",
                               "Here is").replace("The full report is attached.", "")), use_container_width=True)
            if st.button("Remove company", key=f"grow_co_rm_{c['id']}", type="tertiary"):
                _delete(supabase, "companies", c["id"])
                st.rerun()


# ================================================================== 9. Team leaderboard
def team_board(actions, payments, days=30):
    if actions is None or actions.empty:
        return []
    a = actions.copy()
    for c in ("assigned_to", "created_by", "contacted_at", "completed_at", "outcome"):
        if c not in a.columns:
            a[c] = None
    a["who"] = a["assigned_to"].fillna(a["created_by"]).fillna("Owner").replace("", "Owner")
    since = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
    touched = pd.to_datetime(a["contacted_at"].fillna(a["completed_at"]), errors="coerce", utc=True, format="ISO8601")
    done_at = pd.to_datetime(a["completed_at"], errors="coerce", utc=True, format="ISO8601")
    a["worked"] = touched >= since
    a["kept"] = (a["status"] == "Done") & (a["outcome"] == "Retained") & (done_at >= since)
    a["lost"] = (a["status"] == "Done") & (a["outcome"] == "Cancelled") & (done_at >= since)
    money = {}
    if payments is not None and len(payments) and "action_id" in payments.columns:
        p = payments[payments["action_id"].notna()]
        paid = pd.to_datetime(p["paid_on"], errors="coerce")
        p = p[paid >= pd.Timestamp.now() - pd.Timedelta(days=days)]
        owner_of = a.set_index("id")["who"].to_dict()
        for _, r in p.iterrows():
            w = owner_of.get(r["action_id"])
            if w:
                money[w] = money.get(w, 0) + float(r["amount"] or 0)
    out = []
    for who, g in a.groupby("who"):
        decided = int(g["kept"].sum() + g["lost"].sum())
        out.append({"who": who, "worked": int(g["worked"].sum()), "kept": int(g["kept"].sum()),
                    "money": money.get(who, 0.0), "save_rate": g["kept"].sum() / decided if decided else None})
    return sorted(out, key=lambda r: (-r["money"], -r["kept"], -r["worked"]))


def render_team(supabase, gym_id, assess_fn):
    st.caption("Who worked the plays and how much money they kept in the last 30 days. Money only counts "
               "renewal payments credited to that person's plays.")
    import gympulse_revenue as gr
    actions = gw.load_actions(supabase, gym_id, include_archived=True)
    pays = gr.load_payments(supabase, gym_id)
    board = [r for r in team_board(actions, pays) if r["worked"] or r["kept"] or r["money"]]
    if not board:
        st.info("No plays yet. Assign plays to your team in the Action Centre to start the leaderboard.")
        return
    for i, r in enumerate(board):
        medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i + 1}."
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
            c1.markdown(f"### {medal} {r['who']}")
            c2.metric("Money kept", _money(r["money"]))
            c3.metric("Members kept", r["kept"])
            c4.metric("Plays worked", r["worked"], help="Contacted or closed in the last 30 days")
            if r["save_rate"] is not None:
                st.caption(f"Save rate {r['save_rate']:.0%} of decided plays")
    lead = board[0]
    if lead["money"] or lead["kept"]:
        biz, _ = _biz()
        st.link_button("Celebrate the team on WhatsApp", wa_url("", (
            f"🏆 {biz} retention leaderboard, last 30 days\n\n" + "\n".join(
                f"{['🥇', '🥈', '🥉'][i] if i < 3 else str(i + 1) + '.'} {r['who']} · {_money(r['money'])} kept · {r['kept']} members"
                for i, r in enumerate(board[:5])) + "\n\nGreat work, team! 💪")), icon=":material/chat:")


# ================================================================== 10. Season planner
RAMADAN = {2025: (date(2025, 3, 1), date(2025, 3, 30)), 2026: (date(2026, 2, 18), date(2026, 3, 19)),
           2027: (date(2027, 2, 8), date(2027, 3, 9)), 2028: (date(2028, 1, 28), date(2028, 2, 26)),
           2029: (date(2029, 1, 16), date(2029, 2, 14))}
EID_ADHA = {2025: date(2025, 6, 6), 2026: date(2026, 5, 27), 2027: date(2027, 5, 16),
            2028: date(2028, 5, 5), 2029: date(2029, 4, 24)}
EASTER = {2025: date(2025, 4, 20), 2026: date(2026, 4, 5), 2027: date(2027, 3, 28),
          2028: date(2028, 4, 16), 2029: date(2029, 4, 1)}


def seasons(year):
    """Nigerian calendar moments that move gym attendance. Islamic dates are estimates (moon sighting)."""
    ev = [
        ("New Year rush", date(year, 1, 2), date(year, 2, 15), "rush",
         "The busiest joining season. New members who don't build a habit by February quit.",
         "Run the first-90-days programme hard, and start a January consistency challenge.",
         "New year, new you at {biz}! 🎉 Start the year strong with us. Reply JOIN and I'll get you set up. 💪"),
        ("Valentine's", date(year, 2, 1), date(year, 2, 14), "opportunity",
         "Couples and friends sign up together.",
         "Offer a couples or bring-your-partner deal.",
         "Train together, stay together ❤️ Bring your partner to {biz} this February. Reply LOVE for the couples offer!"),
        ("Easter break", EASTER.get(year, date(year, 4, 10)) - timedelta(days=3), EASTER.get(year, date(year, 4, 10)) + timedelta(days=1),
         "dip", "A long weekend: travel and family time.",
         "Post holiday opening hours and offer a quick-return session.",
         "Happy Easter from {biz}! 🐣 We're open over the break. Come burn off the chocolate! 💪"),
        ("Rainy season", date(year, 6, 1), date(year, 9, 30), "dip",
         "Heavy rain and traffic keep people at home, especially evening members.",
         "Push early-morning sessions, short express workouts and home-workout tips. Watch the risk list.",
         "Rain or shine, we've got you ☔ Try our 30-minute express sessions at {biz} this week. Reply YES to book!"),
        ("Summer holidays", date(year, 7, 15), date(year, 9, 10), "dip",
         "Travel and school holidays: parents' routines change.",
         "Offer freezes before trips and family or teen sessions.",
         "Travelling this summer? ✈️ Freeze your {biz} membership so you don't lose any days. Reply FREEZE!"),
        ("Back to routine", date(year, 9, 8), date(year, 10, 15), "opportunity",
         "Schools resume and routines return. A second joining season.",
         "Run a win-back campaign for everyone who lapsed in the summer.",
         "Back to routine? So are we 💪 Come back to {biz} this month. Your spot is still here!"),
        ("Pre-December body goals", date(year, 10, 15), date(year, 11, 30), "opportunity",
         "People want to look good for December parties and owambes.",
         "Launch an 'Owambe ready' or 'Detty December' challenge.",
         "December is coming 🔥 Join our 6-week Detty December body challenge at {biz}. Reply READY to join!"),
        ("Detty December", date(year, 12, 1), date(year + 1, 1, 1), "dip",
         "Travel, parties and the Japa visit season: the biggest drop of the year.",
         "Offer freezes for travellers and a 'see you in January' plan for everyone else.",
         "Travelling for December? 🎄 Freeze your {biz} membership instead of losing it. Reply FREEZE and I'll sort it!"),
    ]
    if year in RAMADAN:
        a, b = RAMADAN[year]
        ev.append(("Ramadan (estimated)", a, b, "dip",
                   "Fasting members change their times. Daytime visits drop and late-evening ones rise.",
                   "Add after-iftar sessions and lighter workouts, and offer freezes.",
                   "Ramadan Kareem from {biz} 🌙 We've added late-evening sessions after iftar. Reply YES for the times!"))
        ev.append(("Eid al-Fitr (estimated)", b + timedelta(days=1), b + timedelta(days=3), "dip",
                   "Public holiday and celebrations.", "Post holiday hours and welcome members back after.",
                   "Eid Mubarak from all of us at {biz}! 🌙 We can't wait to see you back this week. 💪"))
    if year in EID_ADHA:
        d = EID_ADHA[year]
        ev.append(("Eid al-Adha (estimated)", d - timedelta(days=1), d + timedelta(days=2), "dip",
                   "Public holiday and travel.", "Post holiday hours and send a welcome-back note.",
                   "Barka da Sallah from {biz}! 🐏 We're back to normal hours on {back}. See you soon!"))
    return [{"name": n, "start": s, "end": e, "kind": k, "why": w, "do": d, "msg": m} for n, s, e, k, w, d, m in ev]


def upcoming(today=None, horizon=120):
    today = today or _today()
    out = []
    for y in (today.year, today.year + 1):
        for e in seasons(y):
            if e["end"] >= today and e["start"] <= today + timedelta(days=horizon):
                e["prep_now"] = e["start"] - timedelta(days=14) <= today
                out.append(e)
    seen, uniq = set(), []
    for e in sorted(out, key=lambda e: e["start"]):
        if (e["name"], e["start"]) not in seen:
            seen.add((e["name"], e["start"]))
            uniq.append(e)
    return uniq


def render_seasons(supabase, gym_id):
    st.caption("The moments in the Nigerian year that move gym attendance, with a plan and a ready message "
               "for each. Ramadan and Eid dates are estimates, so confirm them closer to the time.")
    biz, _ = _biz()
    today = _today()
    events = upcoming(today)
    tone = {"rush": "lime", "opportunity": "cyan", "dip": "amber"}
    label = {"rush": "joining rush", "opportunity": "opportunity", "dip": "attendance dip"}
    for i, e in enumerate(events):
        live = e["start"] <= today <= e["end"]
        status = "happening now" if live else (f"starts in {(e['start'] - today).days} days")
        head = f"{e['name']} · {e['start']:%d %b} → {e['end']:%d %b} · {status}"
        with st.expander(("🔔 " if e["prep_now"] and not live else "") + head, expanded=i == 0):
            gw._md(gw.chip(label[e["kind"]], tone[e["kind"]], dot=True)
                   + (gw.chip("prepare now", "red", dot=True) if e["prep_now"] and not live else ""))
            st.markdown(f"**Why it matters:** {e['why']}\n\n**What to do:** {e['do']}")
            msg = e["msg"].format(biz=biz, back=(e["end"] + timedelta(days=1)).strftime("%A %d %B"))
            st.code(msg, language=None)
            st.link_button("Share on WhatsApp", wa_url("", msg), icon=":material/chat:")
    ck = _checkins(supabase, gym_id, 400)
    if len(ck) >= 30:
        st.markdown('<div class="section-label">YOUR GYM\'S OWN YEAR</div>', unsafe_allow_html=True)
        per = ck.drop_duplicates(["member_id", "day"]).assign(m=lambda d: d["at"].dt.to_period("M")) \
            .groupby("m").size()
        import altair as alt
        chart = pd.DataFrame({"Month": [m.strftime("%b %Y") for m in per.index], "order": range(len(per)),
                              "Visits": per.values})
        st.altair_chart(alt.Chart(chart).mark_bar(color="#22D3EE", cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
            x=alt.X("Month:N", sort=alt.SortField("order"), title=None), y=alt.Y("Visits:Q", title="Visits")
        ).properties(height=220), use_container_width=True)
        full = per[per.index < pd.Period(today, "M")]
        if len(full) >= 3:
            low = full.idxmin()
            st.caption(f"Your quietest full month so far was {low.strftime('%B %Y')} ({int(full.min())} visits). "
                       "Plan a campaign two weeks before it next year.")
    st.caption("Fuel price and cost-of-living spikes can't be predicted. When one hits, use the 'Price' advice in "
               "Why they left and offer freezes or off-peak plans.")


# ================================================================== 11. Monthly report
def month_bounds(ref=None):
    ref = ref or _today()
    first_this = ref.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    return last_prev.replace(day=1), last_prev


def monthly_data(supabase, gym_id, assess_fn, start, end):
    import gympulse_revenue as gr
    actions = gw.load_actions(supabase, gym_id, include_archived=True)
    pays = gr.load_payments(supabase, gym_id)
    df = _members(supabase, gym_id)
    d = {"start": start, "end": end}
    s, e = pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(days=1)
    kept = pd.DataFrame(columns=["member_id"])
    if actions is not None and len(actions) and "completed_at" in actions.columns:
        done_at = pd.to_datetime(actions["completed_at"], errors="coerce", utc=True, format="ISO8601").dt.tz_localize(None)
        win = actions[(done_at >= s) & (done_at < e) & (actions["status"] == "Done")]
        kept = win[win.get("outcome") == "Retained"].drop_duplicates("member_id") if "outcome" in win else win.iloc[0:0]
        d["kept_n"] = len(kept)
        d["lost_n"] = int((win.get("outcome") == "Cancelled").sum()) if "outcome" in win else 0
    else:
        d["kept_n"] = d["lost_n"] = 0
    d["credited"] = d["collected"] = d["recovered"] = 0.0
    if pays is not None and len(pays):
        paid = pd.to_datetime(pays["paid_on"], errors="coerce")
        p = pays[(paid >= s) & (paid < e)]
        d["collected"] = float(pd.to_numeric(p["amount"], errors="coerce").fillna(0).sum())
        d["credited"] = float(pd.to_numeric(p[p["action_id"].notna()]["amount"], errors="coerce").fillna(0).sum()) \
            if "action_id" in p else 0.0
        d["recovered"] = float(pd.to_numeric(p[p["kind"] == "recovered"]["amount"], errors="coerce").fillna(0).sum()) \
            if "kind" in p else 0.0
    if d["credited"] == 0 and d["kept_n"] and len(df):
        fees = df.set_index("id")["monthly_fee"]
        d["credited"] = float(fees.reindex(kept["member_id"]).fillna(0).sum())
        d["credited_is_fee"] = True
    d["joined"] = int(sum(1 for j in df["joined"] if _has_date(j) and start <= j <= end)) if len(df) else 0
    d["lapsed"] = int(sum(1 for x in df["end"] if _has_date(x) and start <= x <= end)) if len(df) else 0
    ck = _checkins(supabase, gym_id, max((_today() - start).days + 2, 35))
    m = ck[(ck["at"] >= s) & (ck["at"] < e)] if len(ck) else ck
    d["visits"] = int(len(m.drop_duplicates(["member_id", "day"]))) if len(m) else 0
    d["active"] = int(m["member_id"].nunique()) if len(m) else 0
    board = team_board(actions, pays, days=max((_today() - start).days, 1))
    d["top_staff"] = board[0]["who"] if board and (board[0]["kept"] or board[0]["money"]) else None
    reasons = _rows(supabase, "exit_reasons", gym_id) or []
    rs = [r["reason"] for r in reasons if s <= pd.Timestamp(str(r["created_at"])[:10]) < e]
    d["top_reason"] = pd.Series(rs).value_counts().index[0] if rs else None
    return d


def monthly_letter(d):
    """The monthly report as a short, professional letter for email."""
    biz, owner = _biz()
    month = d["start"].strftime("%B %Y")
    lines = [f"Here is {biz}'s retention report for {month}. The full report is attached as a PDF.", ""]
    if d["kept_n"]:
        lines.append(f"Members kept after a retention play: {d['kept_n']}, worth {_money(d['credited'])}"
                     + (" a month." if d.get("credited_is_fee") else "."))
    else:
        lines.append("No plays were closed as kept this month.")
    lines += [f"Payments collected: {_money(d['collected'])}" + (f", including {_money(d['recovered'])} won back."
                                                                 if d["recovered"] else "."),
              f"New members: {d['joined']}.", f"Memberships that ended: {d['lapsed']}.",
              f"Visits: {d['visits']} from {d['active']} active members."]
    if d["top_staff"]:
        lines.append(f"Top of the team: {d['top_staff']}.")
    if d["top_reason"]:
        lines.append(f"Main reason members left: {d['top_reason']}.")
    lines += ["", "Open GymPulse AI to see this week's priorities."]
    return "\n".join(lines)


def monthly_pdf(d):
    import gympulse_reports as rp
    blocks = [("kpis", [("Members kept", str(d["kept_n"]), "after a play"),
                        ("Money kept", _money(d["credited"]), "per month" if d.get("credited_is_fee") else "credited payments"),
                        ("Collected", _money(d["collected"]), "all payments"),
                        ("New members", str(d["joined"]), "joined this month")]),
              ("kpis", [("Visits", str(d["visits"]), "one per member per day"),
                        ("Active members", str(d["active"]), "trained at least once"),
                        ("Ended", str(d["lapsed"]), "memberships that ended"),
                        ("Lost after a play", str(d["lost_n"]), "")]),
              ("h", "Summary"),
              ("p", "<br/>".join(gw._esc(x) for x in monthly_letter(d).split("\n")[2:])),
              ("note", "Money kept counts renewal payments credited to retention plays. Where none were recorded, "
                       "it shows the kept members' monthly fees.")]
    return rp.build_pdf(f"{d['start']:%B %Y} retention report", f"{d['start']:%d %b} – {d['end']:%d %b %Y}", blocks)


def render_monthly(supabase, gym_id, assess_fn, owner_id):
    st.caption("Your month at a glance: members kept, money kept, new joins and visits. GymPulse AI emails "
               "you this report, with the PDF, on the 1st of every month.")
    today = _today()
    which = st.radio("Period", ["Last month", "This month so far"], horizontal=True, key="grow_mr_period")
    start, end = month_bounds(today) if which == "Last month" else (today.replace(day=1), today)
    d = monthly_data(supabase, gym_id, assess_fn, start, end)
    gw.kpi_row([("Members kept", str(d["kept_n"]), "lime", "after a play"),
                ("Money kept", _money(d["credited"]), "cyan", "credited payments" if not d.get("credited_is_fee") else "monthly fees"),
                ("Collected", _money(d["collected"]), "amber", "all payments"),
                ("New members", str(d["joined"]), "grey", "")])
    gw.kpi_row([("Visits", str(d["visits"]), "cyan", "one per member per day"),
                ("Active members", str(d["active"]), "lime", "trained at least once"),
                ("Memberships ended", str(d["lapsed"]), "amber", ""),
                ("Top of the team", d["top_staff"] or "–", "grey", d["top_reason"] and f"Main reason left: {d['top_reason']}" or "")])
    import gympulse_reports as rp
    try:
        rp.download_link("Download the report (PDF)", monthly_pdf(d),
                         f"{safe_name(_biz()[0])}-{start:%Y-%m}-retention-report.pdf", rp.PDF,
                         f"grow_mr_pdf_{which}", primary=True)
    except Exception as error:
        st.error(f"Could not build the PDF: {error}")


def render_month_banner(supabase, gym_id, assess_fn, owner_id):
    """On the dashboard in the first week of a month: last month's result. GymPulse AI emails it to the owner."""
    today = _today()
    if today.day > 7:
        return
    start, end = month_bounds(today)
    try:
        d = monthly_data(supabase, gym_id, assess_fn, start, end)
    except Exception:
        return
    msg = (f"<b>Your {start:%B} report is ready.</b> GymPulse AI helped you keep {d['kept_n']} "
           f"member{'s' if d['kept_n'] != 1 else ''}, worth {_money(d['credited'])}." if d["kept_n"]
           else f"<b>Your {start:%B} report is ready.</b> {_money(d['collected'])} collected, {d['joined']} new members.")
    c1, c2 = st.columns([4, 1])
    gw._md(f'<div class="cc-brief">{msg}</div>', c1)
    c2.button("Open report", key="grow_mr_open", use_container_width=True, on_click=_open_report)


def _open_report():
    st.session_state["grow_section"] = "Monthly report"
    st.session_state["current_page"] = "Grow"


# ================================================================== page
def render_grow(supabase, gym_id, assess_fn, owner_id):
    gw.page_header("Grow", "Tools that keep members longer and bring new ones in.", "Retention toolkit")
    flash = st.session_state.pop("grow_flash", None)
    if flash:
        st.success(flash)
    err = st.session_state.pop("grow_error", None)
    if err:
        st.error(err)
    st.session_state.setdefault("grow_section", SECTIONS[0])
    section = st.segmented_control("Grow section", SECTIONS, key="grow_section",
                                   label_visibility="collapsed") or SECTIONS[0]
    if section == "Collect renewals":
        render_collect(supabase, gym_id, owner_id)
    elif section == "Automatic messages":
        import gympulse_loyalty as gl
        gl.render_auto(supabase, gym_id, owner_id)
    elif section == "Loyalty":
        import gympulse_loyalty as gl
        gl.render_loyalty(supabase, gym_id, owner_id)
    elif section == "New members":
        render_onboarding(supabase, gym_id)
    elif section == "Freeze":
        render_freeze(supabase, gym_id)
    elif section == "Why they left":
        render_exit(supabase, gym_id)
    elif section == "Progress":
        render_progress(supabase, gym_id)
    elif section == "Referrals":
        render_referrals(supabase, gym_id, owner_id)
    elif section == "Challenges":
        render_challenges(supabase, gym_id)
    elif section == "Corporate":
        render_corporate(supabase, gym_id)
    elif section == "Team":
        render_team(supabase, gym_id, assess_fn)
    elif section == "Season planner":
        render_seasons(supabase, gym_id)
    elif section == "Monthly report":
        render_monthly(supabase, gym_id, assess_fn, owner_id)
