"""GymPulse AI · Personal trainer workspace ("My workspace").

A trainer signs in with their own login (Owner → Team & access → Personal trainer) and sees only this:
  Today          today's sessions in time order: mark done / missed / cancelled, book a session
  Timetable      the week, day by day, with dates and times (and their working hours)
  My clients     members who train with them: contact, membership, sessions this month, next session
  Availability   the hours they work on each weekday
  Weekly report  this week's numbers filled in automatically, plus their notes, sent to the owner

The owner sees every trainer's timetable and weekly reports on the Owner page (render_owner_view).
Database: sql/phase35_trainer_workspace.sql (pt_sessions, trainer_availability, trainer_reports).
"""
from datetime import datetime, time, timedelta, timezone

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

SQL_HINT = ("The trainer workspace needs a quick setup: in Supabase open SQL Editor and run "
            "sql/phase35_trainer_workspace.sql.")
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
LENGTHS = [30, 45, 60, 75, 90, 120]
TIMES = list(range(5 * 60, 23 * 60, 15))           # booking times: 5am to 10:45pm, every 15 minutes
STATUS = {"booked": ("Booked", "cyan"), "done": ("Done", "lime"), "missed": ("Missed", "red"),
          "cancelled": ("Cancelled", "grey")}
REPORT_FIELDS = [("wins", "Highlights and client wins"), ("progress", "Client progress (weights, measurements, goals)"),
                 ("concerns", "Concerns: clients at risk, missed sessions, injuries"),
                 ("plan", "Plan for next week")]


def clock(minutes):
    h, m = divmod(int(minutes) % 1440, 60)
    return f"{h % 12 or 12}:{m:02d}{'am' if h < 12 else 'pm'}"


def _local(ts):
    t = pd.to_datetime(ts, utc=True, errors="coerce")
    return None if pd.isna(t) else t.tz_convert(gw.APP_TZ).to_pydatetime()


def week_start(d):
    return d - timedelta(days=d.weekday())


# ------------------------------------------------------------------ data
def _trainer(supabase, gym_id, tid):
    return next((t for t in gw.load_trainers(supabase, gym_id) if str(t.get("id")) == str(tid)), None)


def sessions(supabase, gym_id, tid, start, end):
    """Sessions from start (date) up to end (date, exclusive), oldest first, with local datetimes."""
    a = datetime.combine(start, time.min, gw.APP_TZ).astimezone(timezone.utc).isoformat()
    b = datetime.combine(end, time.min, gw.APP_TZ).astimezone(timezone.utc).isoformat()
    q = supabase.table("pt_sessions").select("*").eq("gym_id", gym_id).gte("starts_at", a).lt("starts_at", b)
    if tid:
        q = q.eq("trainer_id", tid)
    rows = gw.fetch_all(q.order("starts_at"))
    for r in rows:
        r["_at"] = _local(r.get("starts_at"))
        r["status"] = r.get("status") or "booked"
    return [r for r in rows if r["_at"]]


def clients(supabase, gym_id, tid):
    """Members who train with this trainer (has_pt and this trainer picked)."""
    try:
        df, _ = gw.fetch_members(supabase, gym_id, archived=False, include_photo=False)
    except Exception:
        return pd.DataFrame()
    if df.empty or "pt_trainer_id" not in df.columns:
        return pd.DataFrame()
    mine = df[df["has_pt"] & (df["pt_trainer_id"].astype(str) == str(tid))]
    return mine.sort_values("full_name").reset_index(drop=True)


def availability(supabase, tid):
    try:
        rows = supabase.table("trainer_availability").select("*").eq("trainer_id", tid).execute().data or []
    except Exception:
        return None
    return {int(r["dow"]): (int(r["start_min"]), int(r["end_min"])) for r in rows}


def book(supabase, gym_id, tid, member_id, when, minutes, notes, existing):
    """Book a session. Returns an error message, or "" when booked. Stops double-booking."""
    end = when + timedelta(minutes=minutes)
    for r in existing:
        if r.get("status") == "cancelled":
            continue
        a = r["_at"]
        b = a + timedelta(minutes=int(r.get("minutes") or 60))
        if a < end and when < b:
            return f"You already have a session at {a:%H:%M} on {a:%a %d %b}. Pick another time."
    supabase.table("pt_sessions").insert({
        "gym_id": gym_id, "trainer_id": tid, "member_id": member_id, "minutes": int(minutes), "status": "booked",
        "starts_at": when.astimezone(timezone.utc).isoformat(), "notes": notes.strip() or None}).execute()
    return ""


def set_status(supabase, gym_id, sid, status):
    supabase.table("pt_sessions").update({"status": status}).eq("id", sid).eq("gym_id", gym_id).execute()


# ------------------------------------------------------------------ pieces
def _session_row(supabase, gym_id, r, names, key, actions=True):
    label, tone = STATUS.get(r.get("status"), ("Booked", "cyan"))
    who = names.get(r.get("member_id"), "Client")
    mins = int(r.get("minutes") or 60)
    end = r["_at"] + timedelta(minutes=mins)
    with st.container(border=True, key=f"pts_{key}_{r['id']}"):
        a, b = st.columns([3, 2], vertical_alignment="center")
        gw._md(f'<div style="font-weight:800;font-size:17px">{r["_at"]:%H:%M} – {end:%H:%M}</div>'
               f'<div>{gw._esc(who)} · {mins} min</div>'
               + (f'<div class="why" style="padding-top:4px">{gw._esc(r["notes"])}</div>' if r.get("notes") else ""), a)
        gw._md(f'<div class="chip-row" style="justify-content:flex-end">{gw.chip(label, tone, dot=True)}</div>', b)
        if actions and r.get("status") == "booked":
            c1, c2, c3 = st.columns(3)
            for col, (st_key, text) in zip((c1, c2, c3), (("done", "Done"), ("missed", "Missed"),
                                                           ("cancelled", "Cancel"))):
                if col.button(text, key=f"pts_{key}_{st_key}_{r['id']}", use_container_width=True,
                              type="primary" if st_key == "done" else "secondary"):
                    set_status(supabase, gym_id, r["id"], st_key)
                    st.session_state["ptw_flash"] = f"{who}'s session marked {STATUS[st_key][0].lower()}."
                    st.rerun()


def _book_form(supabase, gym_id, tid, roster, avail, key):
    """Book a session with a client (their own clients first, then any member)."""
    mine = st.session_state.get("_ptw_clients", [])
    ids = mine + [i for i in roster if i not in mine]
    if not ids:
        st.caption("No members yet.")
        return
    with st.form(f"ptw_book_{key}", clear_on_submit=True):
        who = st.selectbox("Client", ids, format_func=lambda i: roster[i] + ("" if i in mine else " (not your client yet)"))
        c1, c2, c3 = st.columns(3)
        day = c1.date_input("Date", value=gw.today_local(), min_value=gw.today_local() - timedelta(days=1))
        at = c2.selectbox("Time", TIMES, index=TIMES.index(7 * 60), format_func=clock)
        mins = c3.selectbox("Length", LENGTHS, index=LENGTHS.index(60), format_func=lambda m: f"{m} min")
        notes = st.text_input("Notes (optional)", placeholder="e.g. Leg day, check squat form")
        go = st.form_submit_button("Book session", type="primary", use_container_width=True)
    if go:
        when = datetime.combine(day, time(at // 60, at % 60), gw.APP_TZ)
        hours = (avail or {}).get(day.weekday())
        if avail and (hours is None or not (hours[0] <= at and at + mins <= hours[1])):
            st.warning("That's outside your working hours in Availability. It's booked anyway.")
        existing = sessions(supabase, gym_id, tid, day, day + timedelta(days=1))
        err = book(supabase, gym_id, tid, who, when, mins, notes, existing)
        if err:
            st.error(err)
        else:
            st.session_state["ptw_flash"] = f"Booked {roster[who]} on {when:%a %d %b} at {when:%H:%M}."
            st.rerun()


# ------------------------------------------------------------------ the workspace
def render(supabase, gym_id):
    import gympulse_team as gteam
    tid = gteam.trainer_id() if gteam.is_trainer() else st.session_state.get("ptw_owner_trainer")
    gw.page_header("My workspace" if gteam.is_trainer() else "Trainer workspace",
                   "Your sessions, timetable, clients, working hours and weekly report.", "Personal trainer")
    flash = st.session_state.pop("ptw_flash", None)
    if flash:
        st.success(flash)
    if not tid:
        st.info("Your login isn't linked to a trainer profile yet. Ask the gym owner to link it "
                "(Owner → Team & access).")
        return
    trainer = _trainer(supabase, gym_id, tid) or {}
    try:
        today_rows = sessions(supabase, gym_id, tid, gw.today_local(), gw.today_local() + timedelta(days=1))
    except Exception:
        st.info(SQL_HINT)
        return
    mine = clients(supabase, gym_id, tid)
    st.session_state["_ptw_clients"] = list(mine["id"]) if not mine.empty else []
    try:
        all_members, _ = gw.fetch_members(supabase, gym_id, archived=False, include_photo=False)
        roster = dict(zip(all_members["id"], all_members["full_name"]))
    except Exception:
        roster = {}
    names = dict(roster)
    avail = availability(supabase, tid)

    tabs = st.tabs(["Today", "Timetable", "My clients", "Availability", "Weekly report"], key="ptw_tabs")
    with tabs[0]:
        _today(supabase, gym_id, tid, trainer, today_rows, mine, names, roster, avail)
    with tabs[1]:
        _timetable(supabase, gym_id, tid, names, avail)
    with tabs[2]:
        _clients(supabase, gym_id, tid, mine)
    with tabs[3]:
        _availability(supabase, gym_id, tid, avail)
    with tabs[4]:
        _report(supabase, gym_id, tid, trainer, mine, names)


def _today(supabase, gym_id, tid, trainer, rows, mine, names, roster, avail):
    today = gw.today_local()
    ws = week_start(today)
    week = sessions(supabase, gym_id, tid, ws, ws + timedelta(days=7))
    live = [r for r in rows if r.get("status") != "cancelled"]
    left = [r for r in live if r.get("status") == "booked" and r["_at"] >= datetime.now(gw.APP_TZ) - timedelta(minutes=30)]
    hours = (avail or {}).get(today.weekday())
    gw.kpi_row([
        ("Sessions today", len(live), "cyan", f"{len(left)} still to go"),
        ("My clients", len(mine), "lime", "train with you"),
        ("Done this week", sum(1 for r in week if r.get("status") == "done"), "lime",
         f"{sum(1 for r in week if r.get('status') == 'missed')} missed"),
        ("Working today", f"{clock(hours[0])}–{clock(hours[1])}" if hours else ("Off" if avail else "Not set"),
         "white", "set in Availability"),
    ])
    st.markdown(f'<div class="section-label">TODAY · {today:%A %d %B}</div>', unsafe_allow_html=True)
    if not rows:
        st.caption("No sessions booked today.")
    for r in rows:
        _session_row(supabase, gym_id, r, names, "today")
    with st.expander("Book a session", icon=":material/add:"):
        _book_form(supabase, gym_id, tid, roster, avail, "today")


def _timetable(supabase, gym_id, tid, names, avail):
    off = st.segmented_control("Week", ["Last week", "This week", "Next week"], default="This week",
                               key="ptw_week", label_visibility="collapsed") or "This week"
    ws = week_start(gw.today_local()) + timedelta(days={"Last week": -7, "This week": 0, "Next week": 7}[off])
    rows = sessions(supabase, gym_id, tid, ws, ws + timedelta(days=7))
    by_day = {}
    for r in rows:
        by_day.setdefault(r["_at"].date(), []).append(r)
    st.caption(f"{ws:%d %b} – {ws + timedelta(days=6):%d %b %Y} · "
               f"{sum(1 for r in rows if r.get('status') != 'cancelled')} sessions")
    for i in range(7):
        d = ws + timedelta(days=i)
        hours = (avail or {}).get(i)
        work = f"{clock(hours[0])}–{clock(hours[1])}" if hours else ("Off" if avail else "")
        st.markdown(f"**{d:%A %d %b}**" + (" · today" if d == gw.today_local() else "")
                    + (f" <span style='color:var(--gp-muted,#93A0B4)'>· {work}</span>" if work else ""),
                    unsafe_allow_html=True)
        day_rows = by_day.get(d, [])
        if not day_rows:
            st.caption("No sessions.")
        for r in day_rows:
            _session_row(supabase, gym_id, r, names, f"tt{i}", actions=d >= gw.today_local() - timedelta(days=1))


def _clients(supabase, gym_id, tid, mine):
    if mine.empty:
        st.info("No clients yet. A member becomes your client when the gym marks them “Has a personal trainer” "
                "and picks you (their profile → Edit details).")
        return
    today = gw.today_local()
    month = today.replace(day=1)
    rows = sessions(supabase, gym_id, tid, month, today + timedelta(days=60))
    out = []
    for _, m in mine.iterrows():
        mrows = [r for r in rows if r.get("member_id") == m["id"]]
        done = sum(1 for r in mrows if r.get("status") == "done" and r["_at"].date() >= month)
        nxt = next((r["_at"] for r in mrows if r.get("status") == "booked" and r["_at"].date() >= today), None)
        state = gw.membership_state(m.get("membership_end"))
        out.append({"Client": m["full_name"], "Phone": gw._text(m.get("phone"), "–"),
                    "Goal": gw._text(m.get("fitness_goal"), "–"), "Membership": state["label"],
                    "Sessions this month": done, "Next session": f"{nxt:%a %d %b %H:%M}" if nxt else "Not booked"})
    gw.table(out, pills={"Membership": {}})
    ids = list(mine["id"])
    who = st.selectbox("Open a client's profile", ids, key="ptw_client_pick",
                       format_func=lambda i: mine.set_index("id").loc[i, "full_name"])
    st.button("Open profile", key="ptw_open_profile", on_click=gw.open_profile, args=(who, "My workspace"),
              icon=":material/person:")


def _availability(supabase, gym_id, tid, avail):
    import gympulse_train as gtr
    if avail is None:
        st.info(SQL_HINT)
        return
    st.caption("Your working hours. They show on your timetable, and booking outside them gives a warning.")
    with st.form("ptw_avail"):
        picked = {}
        for i, d in enumerate(DAYS):
            cur = avail.get(i)
            c0, c1, c2 = st.columns([1.3, 1, 1], vertical_alignment="bottom")
            on = c0.checkbox(d, value=cur is not None, key=f"ptw_av_on_{i}")
            s = cur[0] if cur else 6 * 60
            e = cur[1] if cur else 18 * 60
            s = c1.selectbox("From", gtr.OPEN_TIMES, index=gtr.OPEN_TIMES.index(s - s % 5), format_func=clock,
                             key=f"ptw_av_s_{i}")
            e = c2.selectbox("To", gtr.CLOSE_TIMES, index=gtr.CLOSE_TIMES.index(max(5, e - e % 5)),
                             format_func=lambda x: "Midnight" if x == 1440 else clock(x), key=f"ptw_av_e_{i}")
            picked[i] = (int(s), int(e)) if on else None
        go = st.form_submit_button("Save my hours", type="primary", use_container_width=True)
    if go:
        bad = [DAYS[i] for i, v in picked.items() if v and v[1] <= v[0]]
        if bad:
            st.error("The end time must be after the start time: " + ", ".join(bad) + ".")
            return
        supabase.table("trainer_availability").delete().eq("trainer_id", tid).eq("gym_id", gym_id).execute()
        rows = [{"gym_id": gym_id, "trainer_id": tid, "dow": i, "start_min": v[0], "end_min": v[1]}
                for i, v in picked.items() if v]
        if rows:
            supabase.table("trainer_availability").insert(rows).execute()
        st.session_state["ptw_flash"] = "Your working hours are saved."
        st.rerun()


def week_summary(supabase, gym_id, tid, ws, mine):
    rows = sessions(supabase, gym_id, tid, ws, ws + timedelta(days=7))
    live = [r for r in rows if r.get("status") != "cancelled"]
    return {"week": ws.isoformat(), "sessions": len(live),
            "done": sum(1 for r in rows if r.get("status") == "done"),
            "missed": sum(1 for r in rows if r.get("status") == "missed"),
            "cancelled": sum(1 for r in rows if r.get("status") == "cancelled"),
            "clients_seen": len({r.get("member_id") for r in rows if r.get("status") == "done"}),
            "clients": 0 if mine is None or mine.empty else len(mine)}


def _summary_cards(s):
    gw.kpi_row([("Sessions", s.get("sessions", 0), "cyan", "booked this week"),
                ("Done", s.get("done", 0), "lime", f"{s.get('clients_seen', 0)} clients seen"),
                ("Missed", s.get("missed", 0), "red", f"{s.get('cancelled', 0)} cancelled"),
                ("Clients", s.get("clients", 0), "white", "train with you")])


def _report(supabase, gym_id, tid, trainer, mine, names):
    today = gw.today_local()
    weeks = [week_start(today) - timedelta(days=7 * k) for k in range(0, 6)]
    ws = st.selectbox("Week", weeks, key="ptw_rep_week",
                      format_func=lambda d: f"{d:%d %b} – {d + timedelta(days=6):%d %b %Y}"
                      + (" (this week)" if d == weeks[0] else ""))
    try:
        cur = (supabase.table("trainer_reports").select("*").eq("trainer_id", tid)
               .eq("week_start", ws.isoformat()).limit(1).execute().data or [None])[0]
    except Exception:
        st.info(SQL_HINT)
        return
    summary = week_summary(supabase, gym_id, tid, ws, mine)
    _summary_cards(summary)
    body = dict((cur or {}).get("body") or {})
    if cur and cur.get("submitted_at"):
        st.caption(f"Sent to the owner on {_local(cur['submitted_at']):%a %d %b at %H:%M}. You can update it.")
    with st.form(f"ptw_report_{ws}"):
        vals = {k: st.text_area(label, value=gw._text(body.get(k)), key=f"ptw_rep_{k}_{ws}", height=90)
                for k, label in REPORT_FIELDS}
        a, b = st.columns(2)
        save = a.form_submit_button("Save draft", use_container_width=True)
        send = b.form_submit_button("Send to the owner", type="primary", use_container_width=True)
    if save or send:
        row = {"gym_id": gym_id, "trainer_id": tid, "week_start": ws.isoformat(), "summary": summary,
               "body": {k: v.strip() for k, v in vals.items()},
               "updated_at": datetime.now(timezone.utc).isoformat()}
        if send:
            row["submitted_at"] = datetime.now(timezone.utc).isoformat()
        supabase.table("trainer_reports").upsert(row, on_conflict="trainer_id,week_start").execute()
        st.session_state["ptw_flash"] = "Weekly report sent to the owner." if send else "Draft saved."
        st.rerun()


# ------------------------------------------------------------------ the owner's view
def render_owner_view(supabase, gym_id):
    """Owner page → Trainers: each trainer's week and weekly reports."""
    trainers = gw.load_trainers(supabase, gym_id)
    gw.intro("Trainers", ":material/fitness_center:",
             "Each personal trainer's sessions and weekly reports. Give a trainer their own login in Team & access.")
    if not trainers:
        st.info("Add your trainers in Settings → Trainers, then give them a login in Team & access.")
        return
    tmap = {t["id"]: t for t in trainers}
    tid = st.selectbox("Trainer", list(tmap), key="ptw_owner_pick",
                       format_func=lambda i: gw._text(tmap[i].get("full_name"), "Trainer"))
    ws = week_start(gw.today_local())
    try:
        rows = sessions(supabase, gym_id, tid, ws, ws + timedelta(days=7))
        reports = (supabase.table("trainer_reports").select("*").eq("trainer_id", tid)
                   .order("week_start", desc=True).limit(8).execute().data or [])
    except Exception:
        st.info(SQL_HINT)
        return
    _summary_cards(week_summary(supabase, gym_id, tid, ws, clients(supabase, gym_id, tid)))
    try:
        members, _ = gw.fetch_members(supabase, gym_id, include_photo=False)
        names = dict(zip(members["id"], members["full_name"]))
    except Exception:
        names = {}
    st.markdown('<div class="section-label">THIS WEEK</div>', unsafe_allow_html=True)
    gw.table([{"When": f"{r['_at']:%a %d %b %H:%M}", "Client": names.get(r.get("member_id"), "Client"),
               "Length": f"{int(r.get('minutes') or 60)} min", "Status": STATUS.get(r.get("status"), ("Booked",))[0]}
              for r in rows], pills={"Status": {v[0]: v[1] for v in STATUS.values()}},
             empty="No sessions this week.")
    st.markdown('<div class="section-label">WEEKLY REPORTS</div>', unsafe_allow_html=True)
    if not reports:
        st.caption("No reports yet.")
    for rep in reports:
        d = pd.to_datetime(rep["week_start"]).date()
        sent = rep.get("submitted_at")
        with st.expander(f"Week of {d:%d %b %Y} · " + ("Sent" if sent else "Draft")):
            _summary_cards(rep.get("summary") or {})
            body = rep.get("body") or {}
            for k, label in REPORT_FIELDS:
                if gw._text(body.get(k)):
                    st.markdown(f"**{label}**")
                    st.write(body[k])
