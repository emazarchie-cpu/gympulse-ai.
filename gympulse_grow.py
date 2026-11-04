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

SECTIONS = ["Collect renewals", "New members", "Freeze", "Why they left", "Progress",
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


def _member_names(df):
    return {r["id"]: gw._text(r.get("full_name"), "Member") for _, r in df.iterrows()} if len(df) else {}


def _checkins(supabase, gym_id, days=90):
    key = ("grow_ck", gym_id, days)
    ck = gw._cached(key, lambda: gw._fetch_checkins(supabase, gym_id, days=days), ttl=60)
    if ck is None:
        return pd.DataFrame(columns=["member_id", "at", "day"])
    return ck


def wa_url(phone, text):
    digits = gw.whatsapp_digits(phone)
    return f"https://wa.me/{digits}?text={quote(text)}" if digits else f"https://wa.me/?text={quote(text)}"


def send_row(text, phone, key, done_label=None, on_done=None, args=()):
    """WhatsApp button (opens the chat with the message ready) plus an optional 'done' button."""
    c1, c2 = st.columns([1, 1])
    c1.link_button("Open in WhatsApp", wa_url(phone, text), icon=":material/chat:",
                   use_container_width=True)
    if done_label and on_done:
        c2.button(done_label, key=key, on_click=on_done, args=args, use_container_width=True)


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
    plan = row.get("membership_type") if row.get("membership_type") in gw.PLAN_MONTHS else "Monthly"
    return plan, float(row.get("monthly_fee") or 0) * gw.PLAN_MONTHS[plan]


def renewal_text(name, amount, plan, end, pay, ref):
    biz, owner = _biz()
    first = _first(name)
    if end is None:
        when = "is due for renewal"
    else:
        days = (end - _today()).days
        when = (f"ends today" if days == 0 else f"ends in {days} day{'s' if days != 1 else ''} ({end:%d %b})"
                if days > 0 else f"ended on {end:%d %b}")
    lines = [f"Hi {first}! 👋 Your {plan.lower()} membership at {biz} {when}.",
             f"To renew, it's {_money(amount)}."]
    if pay.get("bank_account"):
        lines.append(f"\nPay by bank transfer:\n{pay.get('bank_name', '')}\n{pay['bank_account']}\n"
                     f"{pay.get('bank_holder', '')}\nReference: {ref}")
    if pay.get("paystack_link"):
        lines.append(f"\nOr pay online with card or transfer: {pay['paystack_link']}")
    lines.append("\nSend a screenshot here once you've paid and I'll confirm it straight away. "
                 f"Thank you for training with us! 💪\n{owner}".rstrip())
    return "\n".join(lines)


def _mark_paid(supabase, gym_id, row, amount, plan, method, req_id=None):
    import gympulse_revenue as gr
    end = row.get("end")
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


def _log_request(supabase, gym_id, mid, amount, plan, ref):
    try:
        supabase.table("payment_requests").insert({
            "gym_id": gym_id, "member_id": mid, "amount": float(amount), "plan": plan,
            "reference": ref, "channel": "WhatsApp", "status": "pending"}).execute()
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
        st.caption("These go into every renewal message. Members pay you directly. GymPulse never touches the money.")
        c1, c2, c3 = st.columns(3)
        bank = c1.text_input("Bank", pay.get("bank_name", ""), placeholder="e.g. GTBank")
        acct = c2.text_input("Account number", pay.get("bank_account", ""), placeholder="0123456789")
        holder = c3.text_input("Account name", pay.get("bank_holder", ""), placeholder="e.g. Nuelarch Fitness Ltd")
        link = st.text_input("Paystack payment page (optional)", pay.get("paystack_link", ""),
                             placeholder="e.g. https://paystack.com/pay/your-gym",
                             help="Create a payment page in your Paystack dashboard (Payments → Payment pages) and paste its link.")
        if st.button("Save payment details", type="primary", key="grow_pay_save"):
            _save_settings(supabase, owner_id, {"collect": {"bank_name": bank.strip(), "bank_account": acct.strip(),
                                                           "bank_holder": holder.strip(), "paystack_link": link.strip()}},
                           "Payment details saved.")
            st.rerun()

    df = _members(supabase, gym_id)
    if df.empty:
        st.info("Add members first.")
        return
    reqs = _rows(supabase, "payment_requests", gym_id)
    pending = [r for r in (reqs or []) if r.get("status") == "pending"]
    pending_ids = {r["member_id"] for r in pending}
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
                if age >= 3:
                    c3.link_button("Send a reminder", wa_url(m.get("phone"), renewal_text(
                        m["full_name"], r["amount"], r.get("plan") or "Monthly", m["end"], pay, r["reference"])),
                        use_container_width=True)
                elif c3.button("Cancel request", key=f"grow_rq_x_{r['id']}", use_container_width=True):
                    _update(supabase, "payment_requests", r["id"], {"status": "cancelled"})
                    st.rerun()

    st.markdown('<div class="section-label">ASK FOR PAYMENT</div>', unsafe_allow_html=True)
    if due.empty:
        st.success("Nobody is due in the next 14 days. 🎉")
        return
    if not (pay.get("bank_account") or pay.get("paystack_link")):
        st.warning("Add your bank details or Paystack link above so the messages tell members how to pay.")
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
            plans = list(gw.PLAN_MONTHS)
            plan = c2.selectbox("Plan", plans, index=plans.index(plan), key=f"grow_plan_{m['id']}")
            text = _message_box(renewal_text(m["full_name"], amt, plan, m["end"], pay, ref), f"grow_msg_{m['id']}", 220)
            c1, c2, c3 = st.columns(3)
            c1.link_button("Open in WhatsApp", wa_url(m.get("phone"), text), icon=":material/chat:", use_container_width=True)
            c2.button("I've sent it", key=f"grow_req_{m['id']}", use_container_width=True,
                      on_click=_log_request, args=(supabase, gym_id, m["id"], amt, plan, ref))
            c3.button("Mark as paid", key=f"grow_pd_{m['id']}", type="primary", use_container_width=True,
                      on_click=_mark_paid, args=(supabase, gym_id, m, amt, plan, "Bank transfer"))
            if not gw.whatsapp_digits(m.get("phone")):
                st.caption("No phone number on file. WhatsApp will open without a contact selected.")


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
                text = _message_box(text, f"grow_ob_rescue_{m['id']}")
                send_row(text, m.get("phone"), None)
            if p["next"]:
                t = gw.pick_trainer(trainers, m.get("fitness_goal"))
                st.markdown(f"**{p['next']['title']}**")
                text = _message_box(onboarding_message(p["next"]["text"], m, gw._text((t or {}).get("full_name"))),
                                    f"grow_ob_{m['id']}_{p['next']['step']}")
                send_row(text, m.get("phone"), f"grow_obd_{m['id']}_{p['next']['step']}", "Mark step done",
                         _step_done, (supabase, gym_id, m["id"], p["next"]["step"]))
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
    if extend and m.get("end"):
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
            text = _message_box(f"Hi {_first(m['full_name'])}! 👋 Your break ends soon. We can't wait to have you back at "
                                f"{biz} from {back:%A %d %B}. Want me to book you in for your first session back? 💪\n{owner}",
                                f"grow_fz_msg_{f['id']}")
            send_row(text, m.get("phone"), None)

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
            text = _message_box(exit_survey_text(m["full_name"]), f"grow_ex_msg_{m['id']}", 230)
            st.link_button("Open in WhatsApp", wa_url(m.get("phone"), text), icon=":material/chat:")
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
                text = _message_box(text, f"grow_pg_sh_{m['id']}")
                send_row(text, m.get("phone"), None)
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
                            f"and I'll sort out the rest. 💪\n{owner}", "grow_ref_ask_msg")
        send_row(text, m.get("phone"), None)

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
                    c1.link_button("Tell them their reward", wa_url(referrer.get("phone"),
                                   f"Hi {_first(referrer['full_name'])}! 🎁 {r['friend_name']} just joined {biz} thanks to you. "
                                   f"Your reward: {r.get('reward') or reward}. Thank you! 🙏\n{owner}"), use_container_width=True)
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
        lines = []
        for i, r in board.iterrows():
            n = names.get(r["member_id"], "Member")
            pct = min(100, round(r["visits"] / max(c["target_visits"], 1) * 100))
            medal = ["🥇", "🥈", "🥉"][i] if i < 3 and r["visits"] else f"{i + 1}."
            gw._md(f'<div style="display:flex;align-items:center;gap:12px;margin:6px 0"><div style="width:34px">{medal}</div>'
                   f'<div style="flex:1"><b>{gw._esc(n)}</b> · {r["visits"]}/{c["target_visits"]} visits'
                   f'<div class="pbar" style="margin-top:4px"><span style="width:{pct}%;--tone:#B7F34A"></span></div></div></div>')
            lines.append(f"{medal} {n.split()[0]} · {r['visits']} visits")
        top = "\n".join(lines[:10])
        text = _message_box(f"🏆 {c['name']} leaderboard at {biz}\n\n{top}\n\n"
                            + ("Congratulations to our winners! 🎉" if ended else
                               f"{(date.fromisoformat(c['ends_on']) - today).days} days to go. Every visit counts! 💪"),
                            f"grow_ch_share_{pick}", 230)
        st.link_button("Share the leaderboard on WhatsApp", wa_url("", text), icon=":material/chat:")
        st.caption("Tip: paste it into your members' WhatsApp group.")
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
                import gympulse_reports as rp
                c1, c2 = st.columns(2)
                with c1:
                    try:
                        rp.download_link("Download HR report (PDF)", company_pdf(rep),
                                         f"{c['name']}-attendance-{_today():%Y-%m}.pdf", rp.PDF, f"grow_co_pdf_{c['id']}",
                                         primary=True)
                    except Exception as error:
                        st.error(f"Could not build the PDF: {error}")
                biz, owner = _biz()
                summary = (f"Hi {gw._text(c.get('hr_name'), 'there')}, here's {c['name']}'s gym attendance at {biz} "
                           f"for the last 30 days: {rep['active']} of {rep['enrolled']} staff trained "
                           f"({rep['active_rate']:.0%}), {rep['visits']} visits in total. The full report is attached. "
                           f"Happy to help get the rest of the team started!\n{owner}")
                if c.get("hr_phone"):
                    c2.link_button("Send summary to HR on WhatsApp", wa_url(c["hr_phone"], summary), use_container_width=True)
                elif c.get("hr_email"):
                    c2.link_button("Email HR", f"mailto:{c['hr_email']}?subject={quote(c['name'] + ' gym attendance')}"
                                               f"&body={quote(summary)}", use_container_width=True)
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
    d["joined"] = int(sum(1 for j in df["joined"] if j and start <= j <= end)) if len(df) else 0
    d["lapsed"] = int(sum(1 for x in df["end"] if x and start <= x <= end)) if len(df) else 0
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


def monthly_text(d):
    biz, owner = _biz()
    month = d["start"].strftime("%B %Y")
    money = _money(d["credited"])
    lines = [f"📊 *{biz} · {month} retention report*", ""]
    if d["kept_n"]:
        lines.append(f"✅ GymPulse AI helped you keep *{d['kept_n']} member{'s' if d['kept_n'] != 1 else ''}*, "
                     f"worth *{money}*{' a month' if d.get('credited_is_fee') else ''}.")
    else:
        lines.append("No plays were closed as kept this month. Work your Action Centre to start saving members.")
    lines += [f"💰 Collected: {_money(d['collected'])}" + (f" (incl. {_money(d['recovered'])} won back)" if d["recovered"] else ""),
              f"🆕 New members: {d['joined']}",
              f"⏳ Memberships that ended: {d['lapsed']}",
              f"🏋️ Visits: {d['visits']} from {d['active']} active members"]
    if d["lost_n"]:
        lines.append(f"❌ Members lost after a play: {d['lost_n']}")
    if d["top_staff"]:
        lines.append(f"🏆 Top of the team: {d['top_staff']}")
    if d["top_reason"]:
        lines.append(f"🔎 Main reason members left: {d['top_reason']}")
    lines += ["", "Open GymPulse AI to see this week's priorities: https://usegympulseai.com"]
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
              ("p", monthly_text(d).replace("*", "").split("\n", 2)[-1].replace("\n", "<br/>")),
              ("note", "Money kept counts renewal payments credited to retention plays. Where none were recorded, "
                       "it shows the kept members' monthly fees.")]
    return rp.build_pdf(f"{d['start']:%B %Y} retention report", f"{d['start']:%d %b} – {d['end']:%d %b %Y}", blocks)


def render_monthly(supabase, gym_id, assess_fn, owner_id):
    st.caption("Your month in one message: members kept, money kept, new joins, visits and your top performer. "
               "It's ready on the 1st of every month, and you can see the month so far too.")
    today = _today()
    which = st.radio("Period", ["Last month", "This month so far"], horizontal=True, key="grow_mr_period")
    start, end = month_bounds(today) if which == "Last month" else (today.replace(day=1), today)
    d = monthly_data(supabase, gym_id, assess_fn, start, end)
    gw.kpi_row([("Members kept", str(d["kept_n"]), "lime", "after a play"),
                ("Money kept", _money(d["credited"]), "cyan", "credited payments" if not d.get("credited_is_fee") else "monthly fees"),
                ("Collected", _money(d["collected"]), "amber", "all payments"),
                ("New members", str(d["joined"]), "grey", "")])
    text = monthly_text(d)
    st.text_area("WhatsApp message", text, height=300, key=f"grow_mr_text_{which}")
    s = _settings()
    c1, c2, c3 = st.columns(3)
    c1.link_button("Send to my WhatsApp", wa_url(s.get("biz_phone", ""), text), icon=":material/chat:",
                   use_container_width=True)
    with c2:
        import gympulse_reports as rp
        try:
            rp.download_link("Download PDF", monthly_pdf(d), f"GymPulse-{start:%Y-%m}-report.pdf", rp.PDF,
                             f"grow_mr_pdf_{which}", primary=True)
        except Exception as error:
            st.error(f"Could not build the PDF: {error}")
    owner_email = (st.session_state.get("auth_user") or {}).get("email", "")
    import gympulse_followups as fu
    if owner_email and fu.email_ready():
        if c3.button(f"Email to {owner_email}", key="grow_mr_email", use_container_width=True):
            try:
                fu.send_email(owner_email, f"{_biz()[0]} · {start:%B %Y} retention report", text.replace("*", ""))
                st.success("Report emailed.")
            except Exception as error:
                st.error(f"Could not send: {error}")
    if not s.get("biz_phone"):
        st.caption("Add your business WhatsApp number in Settings → Gym so this opens your own chat.")


def render_month_banner(supabase, gym_id, assess_fn, owner_id):
    """On the dashboard in the first week of a month: last month's result, emailed once automatically."""
    today = _today()
    if today.day > 7:
        return
    start, end = month_bounds(today)
    key = f"{start:%Y-%m}"
    try:
        d = monthly_data(supabase, gym_id, assess_fn, start, end)
    except Exception:
        return
    s = _settings()
    if s.get("monthly_report_sent") != key:
        owner_email = (st.session_state.get("auth_user") or {}).get("email", "")
        import gympulse_followups as fu
        if owner_email and fu.email_ready() and not st.session_state.get(f"_mr_try_{key}"):
            st.session_state[f"_mr_try_{key}"] = True
            try:
                fu.send_email(owner_email, f"{_biz()[0]} · {start:%B %Y} retention report", monthly_text(d).replace("*", ""))
                profile = st.session_state.get("user_profile") or {}
                ns = {**dict(profile.get("settings") or {}), "monthly_report_sent": key}
                supabase.table("profiles").update({"settings": ns}).eq("id", owner_id).execute()
                profile["settings"] = ns
            except Exception:
                pass
    msg = (f"<b>Your {start:%B} report is ready.</b> GymPulse AI helped you keep {d['kept_n']} "
           f"member{'s' if d['kept_n'] != 1 else ''}, worth {_money(d['credited'])}." if d["kept_n"]
           else f"<b>Your {start:%B} report is ready.</b> {_money(d['collected'])} collected, {d['joined']} new members.")
    c1, c2 = st.columns([4, 1])
    gw._md(f'<div class="cc-brief">📊 {msg}</div>', c1)
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
    st.session_state.setdefault("grow_section", SECTIONS[0])
    section = st.segmented_control("Grow section", SECTIONS, key="grow_section",
                                   label_visibility="collapsed") or SECTIONS[0]
    if section == "Collect renewals":
        render_collect(supabase, gym_id, owner_id)
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
