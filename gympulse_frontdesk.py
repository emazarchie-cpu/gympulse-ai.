"""GymPulse AI · Front desk: prospects, cancellation notices, balances owed and today at a glance.

So a gym can run on GymPulse AI alone (sql/phase46_frontdesk.sql):
  - Prospects: people who enquired (walk-in, Instagram, WhatsApp, referral) or signed up online but haven't
    paid. Simple stages, a call for staff when one is due, and one tap to make them a member.
  - Cancellation notices: a member says they want to leave. Staff record it with the leaving date, and a
    "save" call goes to the Action Centre at once: the last chance to keep them.
  - Balances owed: part-payments. Who owes what, add a charge, record a payment.
  - Today at a glance: one row on the Dashboard.
"""
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

SQL_HINT = "This needs a one-time setup: run sql/phase46_frontdesk.sql in Supabase."
SOURCES = {"walk_in": "Walk-in", "website": "Website or sign-up link", "instagram": "Instagram",
           "whatsapp": "WhatsApp", "referral": "Referred by a member", "phone": "Phone call", "other": "Other"}
STAGES = {"new": "New", "contacted": "Contacted", "visited": "Came for a visit", "joined": "Joined",
          "not_interested": "Not interested"}
NOT_INTERESTED = ["Price", "Location", "Joined another gym", "Not ready yet", "No reply", "Other"]
CANCEL_REASONS = ["Price or money", "Moving or travelling", "No time", "Injury or health", "Not seeing results",
                  "Unhappy with the gym", "Other"]
FOLLOW_UP_DAYS = 2


def _now():
    return datetime.now(timezone.utc).isoformat()


def _wa(phone, text):
    d = gw.whatsapp_digits(phone)
    return f"https://wa.me/{d}?text={quote(text)}" if d and len(d) >= 10 else ""


def _gym_name():
    return gw._text((st.session_state.get("user_profile") or {}).get("business_name"), "our gym")


def _naira(x):
    return f"₦{float(x or 0):,.0f}"


# ================================================================== prospects
def load_prospects(supabase, gym_id):
    """Prospect rows, or None when phase 46 hasn't been run."""
    def load():
        try:
            return gw.fetch_all(supabase.table("prospects").select("*").eq("gym_id", gym_id)
                                .order("created_at", desc=True).order("id"))
        except Exception:
            return None
    return gw._cached(("prospects", gym_id), load, ttl=60)


def unpaid_signups(supabase, gym_id, days=60):
    """Members who joined in the last `days` days with no plan set yet: signed up, not paid."""
    members, _ = gw.fetch_members(supabase, gym_id, archived=False, include_photo=False)
    if members.empty:
        return members
    created = pd.to_datetime(members["created_at"], errors="coerce", utc=True)
    recent = created >= pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
    return members[recent & members["membership_end"].isna()].reset_index(drop=True)


def needs_call(p, today=None):
    today = today or gw.today_local()
    if p.get("stage") not in ("new", "contacted", "visited"):
        return False
    due = p.get("next_follow_up")
    if due:
        return str(due)[:10] <= today.isoformat()
    made = pd.to_datetime(p.get("created_at"), errors="coerce", utc=True)
    return p.get("stage") == "new" and not pd.isna(made) and \
        (pd.Timestamp.now(tz="UTC") - made).days >= FOLLOW_UP_DAYS - 1


def _save_prospect(supabase, pid, patch):
    patch = {**patch, "updated_at": _now()}
    supabase.table("prospects").update(patch).eq("id", pid).execute()
    gw.bump_data_version()


def _make_member(supabase, gym_id, p):
    row = {"gym_id": gym_id, "full_name": p["full_name"]}
    for k in ("phone", "email"):
        if gw._text(p.get(k)):
            row[k] = p[k]
    res = supabase.table("members").insert(row).execute().data or []
    mid = res[0]["id"] if res else None
    _save_prospect(supabase, p["id"], {"stage": "joined", "member_id": mid})
    return mid


def render_prospects(supabase, gym_id):
    gw.intro("Prospects", ":material/person_search:",
             "People who asked about the gym or signed up online but haven't paid yet. Call them while they're "
             "interested, and make them a member when they pay.")
    rows = load_prospects(supabase, gym_id)
    if rows is None:
        st.info(SQL_HINT)
        return
    flash = st.session_state.pop("pr_flash", None)
    if flash:
        st.success(flash)
    open_rows = [p for p in rows if p.get("stage") in ("new", "contacted", "visited")]
    month = gw.today_local().replace(day=1).isoformat()
    this_month = [p for p in rows if str(p.get("created_at") or "")[:10] >= month]
    joined = [p for p in this_month if p.get("stage") == "joined"]
    due = [p for p in open_rows if needs_call(p)]
    unpaid = unpaid_signups(supabase, gym_id)
    gw.kpi_row([("Open prospects", str(len(open_rows)), "lime", f"{len(due)} to call today"),
                ("New this month", str(len(this_month)), "white", "enquiries"),
                ("Joined this month", str(len(joined)),
                 "lime", f"{len(joined) / len(this_month):.0%} joined" if this_month else "–"),
                ("Signed up, not paid", str(len(unpaid)), "amber", "last 60 days")])

    with st.expander("Add a prospect", expanded=not rows, icon=":material/person_add:"):
        with st.form("pr_add", clear_on_submit=True, border=False):
            c1, c2 = st.columns(2)
            name = c1.text_input("Full name")
            phone = c2.text_input("Phone or WhatsApp", placeholder="e.g. 0803 000 0000")
            c3, c4 = st.columns(2)
            email = c3.text_input("Email (optional)")
            source = c4.selectbox("Where did they hear about us?", list(SOURCES), format_func=SOURCES.get)
            notes = st.text_input("Notes (optional)", placeholder="e.g. wants weight loss, asked about morning classes")
            if st.form_submit_button("Add prospect", type="primary"):
                if not name.strip():
                    st.error("Add their name.")
                else:
                    supabase.table("prospects").insert({
                        "gym_id": gym_id, "full_name": name.strip(), "phone": phone.strip() or None,
                        "email": email.strip() or None, "source": source, "notes": notes.strip() or None,
                        "next_follow_up": gw.today_local().isoformat()}).execute()
                    gw.bump_data_version()
                    st.session_state["pr_flash"] = f"{name.strip()} added. Call or message them today."
                    st.rerun()

    if len(unpaid):
        with st.expander(f"Signed up online, not paid ({len(unpaid)})", icon=":material/how_to_reg:"):
            st.caption("They joined with your sign-up link or QR code but have no plan yet. Message them, then "
                       "record their first payment on their profile.")
            for _, m in unpaid.head(30).iterrows():
                a, b, c = st.columns([3, 1.2, 1.2], vertical_alignment="center")
                a.markdown(f"**{gw._esc(m['full_name'])}**  \n<small>joined "
                           f"{pd.Timestamp(m['created_at']):%d %b}</small>", unsafe_allow_html=True)
                link = _wa(m.get("phone"), f"Hi {gw._text(m['full_name']).split()[0]}, thanks for signing up at "
                                           f"{_gym_name()}! Shall we get your membership started? You can pay at "
                                           "the front desk or by transfer.")
                if link:
                    b.link_button("WhatsApp", link, use_container_width=True)
                c.button("Profile", key=f"pr_unpaid_{m['id']}", on_click=gw.open_profile,
                         args=(m["id"], "Grow"), use_container_width=True)

    view = st.segmented_control("Show", ["To call", "Open", "Joined", "Not interested"], default="To call",
                                key="pr_view") or "To call"
    pick = {"To call": due, "Open": open_rows,
            "Joined": [p for p in rows if p.get("stage") == "joined"],
            "Not interested": [p for p in rows if p.get("stage") == "not_interested"]}[view]
    if not pick:
        st.caption("No one here." if rows else "No prospects yet. Add your first enquiry above.")
    for p in pick[:60]:
        _prospect_card(supabase, gym_id, p)


def _prospect_card(supabase, gym_id, p):
    first = (gw._text(p["full_name"]).split() or ["there"])[0]
    when = pd.Timestamp(p["created_at"]).tz_convert(gw.APP_TZ)
    with st.container(border=True, key=f"pr_card_{p['id']}"):
        a, b = st.columns([3, 1.4], vertical_alignment="center")
        a.markdown(f"**{gw._esc(p['full_name'])}** · {STAGES.get(p['stage'], p['stage'])}  \n"
                   f"<small>{SOURCES.get(p.get('source'), 'Other')} · added {when:%d %b}"
                   + (f" · {gw._esc(p['notes'])}" if gw._text(p.get("notes")) else "")
                   + (f" · {gw._esc(p['reason'])}" if gw._text(p.get("reason")) else "") + "</small>",
                   unsafe_allow_html=True)
        link = _wa(p.get("phone"), f"Hi {first}, it's {_gym_name()}. Thanks for your interest! When would you "
                                    "like to come in for a visit? We'd love to show you around.")
        if link and p["stage"] not in ("joined", "not_interested"):
            b.link_button("WhatsApp", link, use_container_width=True)
        if p["stage"] in ("joined", "not_interested"):
            return
        c1, c2, c3, c4 = st.columns(4)
        if c1.button("Contacted", key=f"pr_c_{p['id']}", use_container_width=True):
            _save_prospect(supabase, p["id"], {"stage": "contacted", "contacted_at": _now(),
                                               "next_follow_up": (gw.today_local() + timedelta(days=3)).isoformat()})
            st.rerun()
        if c2.button("Came in", key=f"pr_v_{p['id']}", use_container_width=True):
            _save_prospect(supabase, p["id"], {"stage": "visited",
                                               "next_follow_up": (gw.today_local() + timedelta(days=2)).isoformat()})
            st.rerun()
        if c3.button("Make member", key=f"pr_m_{p['id']}", type="primary", use_container_width=True):
            try:
                mid = _make_member(supabase, gym_id, p)
            except Exception:
                st.error("Couldn't add them as a member. Try again.")
                return
            st.session_state["pr_flash"] = f"{p['full_name']} is now a member. Record their first payment on their profile."
            if mid:
                gw.open_profile(mid, "Grow")
            st.rerun()
        with c4.popover("Not interested", use_container_width=True):
            why = st.selectbox("Why?", NOT_INTERESTED, key=f"pr_why_{p['id']}")
            if st.button("Save", key=f"pr_n_{p['id']}"):
                _save_prospect(supabase, p["id"], {"stage": "not_interested", "reason": why, "next_follow_up": None})
                st.rerun()


# ================================================================== cancellation notices
def _members_with(supabase, gym_id, cols):
    try:
        return gw.fetch_all(supabase.table("members").select("id, full_name, phone, membership_end, " + cols)
                            .eq("gym_id", gym_id).eq("archived", False).order("id"))
    except Exception:
        return None


def pending_cancellations(supabase, gym_id):
    rows = gw._cached(("cancels", gym_id), lambda: _members_with(
        supabase, gym_id, "cancel_notice_at, cancel_effective, cancel_reason, cancel_status"), ttl=60)
    if rows is None:
        return None
    return [r for r in rows if r.get("cancel_status") == "pending"]


def render_cancellations(supabase, gym_id):
    gw.intro("Cancellation notices", ":material/logout:",
             "When a member says they want to leave, record it here. GymPulse adds a save call to the Action "
             "Centre straight away: it's your last chance to keep them.")
    pending = pending_cancellations(supabase, gym_id)
    if pending is None:
        st.info(SQL_HINT)
        return
    flash = st.session_state.pop("cn_flash", None)
    if flash:
        st.success(flash)
    members, _ = gw.fetch_members(supabase, gym_id, archived=False, include_photo=False)
    with st.expander("Record a cancellation notice", expanded=not pending, icon=":material/edit_note:"):
        if members.empty:
            st.caption("Add members first.")
        else:
            names = dict(zip(members["id"], members["full_name"]))
            ends = dict(zip(members["id"], members["membership_end"]))
            with st.form("cn_add", border=False):
                mid = st.selectbox("Member", list(names), index=None, format_func=lambda i: names.get(i, ""),
                                   placeholder="Choose a member")
                c1, c2 = st.columns(2)
                reason = c1.selectbox("Reason they gave", CANCEL_REASONS)
                default_end = gw.today_local() + timedelta(days=30)
                leave = c2.date_input("Leaving date", value=default_end,
                                      help="Usually their plan end date or your notice period (e.g. 30 days).")
                if st.form_submit_button("Save notice", type="primary"):
                    if not mid:
                        st.error("Choose the member.")
                    else:
                        _record_notice(supabase, gym_id, mid, names.get(mid), reason, leave)
                        st.session_state["cn_flash"] = (f"Notice saved for {names.get(mid)}. A save call is in the "
                                                        "Action Centre.")
                        st.rerun()
                if mid and ends.get(mid):
                    st.caption(f"Their plan ends {pd.Timestamp(ends[mid]):%d %b %Y}.")

    if not pending:
        st.caption("No one has given notice. Good.")
        return
    st.markdown(f"**{len(pending)} member{'s' if len(pending) != 1 else ''} want{'s' if len(pending) == 1 else ''} "
                "to leave**")
    for r in sorted(pending, key=lambda x: str(x.get("cancel_effective") or "")):
        left = (pd.Timestamp(r["cancel_effective"]).date() - gw.today_local()).days if r.get("cancel_effective") else None
        with st.container(border=True, key=f"cn_card_{r['id']}"):
            a, b = st.columns([3, 1.4], vertical_alignment="center")
            when = f"leaves {pd.Timestamp(r['cancel_effective']):%d %b}" if r.get("cancel_effective") else ""
            if left is not None:
                when += " (today)" if left == 0 else f" (in {left} days)" if left > 0 else " (date passed)"
            a.markdown(f"**{gw._esc(r['full_name'])}** · {gw._esc(r.get('cancel_reason') or '')}  \n<small>{when}</small>",
                       unsafe_allow_html=True)
            b.button("Profile", key=f"cn_p_{r['id']}", on_click=gw.open_profile, args=(r["id"], "Grow"),
                     use_container_width=True)
            c1, c2 = st.columns(2)
            if c1.button("We kept them", key=f"cn_s_{r['id']}", type="primary", use_container_width=True):
                _close_notice(supabase, r["id"], "saved")
                st.session_state["cn_flash"] = f"Great, {r['full_name']} is staying."
                st.rerun()
            if c2.button("They left", key=f"cn_l_{r['id']}", use_container_width=True):
                _close_notice(supabase, r["id"], "left")
                st.session_state["cn_flash"] = (f"Noted. Record why {r['full_name']} left in Why they left, and "
                                                "archive them on their leaving date.")
                st.rerun()


def _record_notice(supabase, gym_id, mid, name, reason, leave):
    supabase.table("members").update({"cancel_notice_at": _now(), "cancel_effective": leave.isoformat(),
                                      "cancel_reason": reason, "cancel_status": "pending"}).eq("id", mid).execute()
    try:
        gw._create_action(supabase, gym_id, mid, "Personal call", 0,
                          note=f"Wants to cancel ({reason}), leaving {leave:%d %b}. Call to understand why and "
                               "offer a fix before they go.")
    except Exception:
        pass
    gw.bump_data_version()


def _close_notice(supabase, mid, outcome):
    supabase.table("members").update({"cancel_status": outcome}).eq("id", mid).execute()
    gw.bump_data_version()


# ================================================================== balances owed
def balances(supabase, gym_id):
    rows = gw._cached(("balances", gym_id), lambda: _members_with(supabase, gym_id, "balance_owed, balance_note"),
                      ttl=60)
    if rows is None:
        return None
    return [r for r in rows if float(r.get("balance_owed") or 0) > 0]


def render_balances(supabase, gym_id):
    gw.intro("Balances owed", ":material/account_balance_wallet:",
             "Members who paid part of their fee and still owe the rest. Add a balance, send a reminder, and "
             "record payments as they come in.")
    owing = balances(supabase, gym_id)
    if owing is None:
        st.info(SQL_HINT)
        return
    flash = st.session_state.pop("bal_flash", None)
    if flash:
        st.success(flash)
    total = sum(float(r["balance_owed"]) for r in owing)
    gw.kpi_row([("Owed to you", _naira(total), "amber", f"{len(owing)} member{'s' if len(owing) != 1 else ''}")])
    members, _ = gw.fetch_members(supabase, gym_id, archived=False, include_photo=False)
    with st.expander("Add a balance owed", expanded=not owing, icon=":material/add_card:"):
        if members.empty:
            st.caption("Add members first.")
        else:
            names = dict(zip(members["id"], members["full_name"]))
            with st.form("bal_add", border=False):
                mid = st.selectbox("Member", list(names), index=None, format_func=lambda i: names.get(i, ""),
                                   placeholder="Choose a member")
                c1, c2 = st.columns(2)
                amount = c1.number_input("Amount they still owe (₦)", min_value=0, step=1000)
                note = c2.text_input("Note (optional)", placeholder="e.g. rest of December fee")
                if st.form_submit_button("Add balance", type="primary"):
                    if not mid or amount <= 0:
                        st.error("Choose the member and the amount.")
                    else:
                        cur = next((float(r.get("balance_owed") or 0) for r in owing if r["id"] == mid), 0.0)
                        supabase.table("members").update({"balance_owed": cur + float(amount),
                                                          "balance_note": note.strip() or None}).eq("id", mid).execute()
                        gw.bump_data_version()
                        st.session_state["bal_flash"] = f"{names.get(mid)} now owes {_naira(cur + amount)}."
                        st.rerun()
    for r in sorted(owing, key=lambda x: -float(x["balance_owed"])):
        first = (gw._text(r["full_name"]).split() or ["there"])[0]
        with st.container(border=True, key=f"bal_card_{r['id']}"):
            a, b = st.columns([3, 1.4], vertical_alignment="center")
            a.markdown(f"**{gw._esc(r['full_name'])}** · owes **{_naira(r['balance_owed'])}**"
                       + (f"  \n<small>{gw._esc(r['balance_note'])}</small>" if gw._text(r.get("balance_note")) else ""),
                       unsafe_allow_html=True)
            link = _wa(r.get("phone"), f"Hi {first}, a friendly reminder from {_gym_name()}: you have a balance of "
                                       f"{_naira(r['balance_owed'])} on your membership. You can pay at the front "
                                       "desk or by transfer. Thank you!")
            if link:
                b.link_button("Remind on WhatsApp", link, use_container_width=True)
            c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
            paid = c1.number_input("Payment received (₦)", min_value=0, step=1000, key=f"bal_amt_{r['id']}")
            if c2.button("Record", key=f"bal_pay_{r['id']}", type="primary", use_container_width=True) and paid > 0:
                left = max(0.0, float(r["balance_owed"]) - float(paid))
                supabase.table("members").update({"balance_owed": left}).eq("id", r["id"]).execute()
                try:
                    supabase.table("payments").insert({"gym_id": gym_id, "member_id": r["id"], "amount": float(paid),
                                                       "paid_on": gw.today_local().isoformat(), "kind": "other",
                                                       "method": "Balance", "note": "Balance payment"}).execute()
                except Exception:
                    pass
                gw.bump_data_version()
                st.session_state["bal_flash"] = (f"{_naira(paid)} recorded for {r['full_name']}. "
                                                 + ("All paid." if left == 0 else f"{_naira(left)} still owed."))
                st.rerun()


# ================================================================== today at a glance (Dashboard)
def render_today(supabase, gym_id):
    """One row: visits today, new members this month, prospects to call, cancellation notices, balances owed."""
    try:
        ck = gw.checkins_window(supabase, gym_id, 90)
        today = pd.Timestamp(gw.today_local())
        visits = int(ck[ck["day"] == today]["member_id"].nunique()) if ck is not None and len(ck) else 0
        members, _ = gw.fetch_members(supabase, gym_id, archived=False, include_photo=False)
        created = pd.to_datetime(members["created_at"], errors="coerce", utc=True) if len(members) else pd.Series(dtype="datetime64[ns, UTC]")
        new = int((created >= pd.Timestamp(gw.today_local().replace(day=1)).tz_localize(gw.APP_TZ)).sum()) if len(members) else 0
    except Exception:
        return
    prospects = load_prospects(supabase, gym_id)
    calls = sum(1 for p in prospects or [] if needs_call(p))
    pending = pending_cancellations(supabase, gym_id) or []
    owing = balances(supabase, gym_id) or []
    total = sum(float(r["balance_owed"]) for r in owing)
    gw.kpi_row([("Visits today", str(visits), "lime", "checked in"),
                ("New this month", str(new), "white", "members"),
                ("Prospects to call", str(calls), "lime" if calls else "white", "Grow → Prospects"),
                ("Leaving", str(len(pending)), "red" if pending else "white", "cancellation notices"),
                ("Owed", _naira(total), "amber" if total else "white",
                 f"{len(owing)} member{'s' if len(owing) != 1 else ''}")])
