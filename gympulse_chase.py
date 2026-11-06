"""GymPulse AI · Automatic follow-up: when an automatic message gets no response, a person takes over.

1. GymPulse sends "We missed you" (or a renewal reminder) automatically.
2. Wait days later (3 by default), if the member hasn't replied, checked in or renewed, a call is added
   to Follow-ups -> Calls, assigned to a staff member, with what to say.
3. Staff tap why the member stopped (moved, money, time, injury, motivation, other). GymPulse shows
   what to offer for that reason.
4. "No answer" tries again 3 days later. After 3 tries the member is marked "No response".
5. When the member checks in or renews, the call closes by itself as Retained.

Calls are ordinary retention plays (retention_actions) with details.chase, so the Action Centre, staff
workload and outcome reports all count them. No new tables.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

CREATED_BY = "auto:follow-up"
MAX_TRIES = 3
RETRY_DAYS = 3
LOOKBACK_DAYS = 21
TRIGGER_KINDS = ("missed", "renewal")

REASONS = {
    "moved": ("Moved or travelling", ":material/flight:",
              "Offer to pause their membership until they're back, or point them to a branch near them."),
    "money": ("Money is tight", ":material/payments:",
              "Offer a cheaper plan or paying monthly. Only offer a discount here, where money is the reason."),
    "time": ("Too busy", ":material/schedule:",
             "Suggest quieter times, shorter classes or a 30-minute plan they can fit in."),
    "injury": ("Injury or health", ":material/healing:",
               "Offer a pause and a check-in later. Suggest a trainer-led return when they're ready."),
    "motivation": ("Lost motivation", ":material/bolt:",
                   "Invite them to a challenge, pair them with a workout buddy or offer a free PT session."),
    "other": ("Something else", ":material/more_horiz:", "Write down what they said so the gym can learn from it."),
}


# ------------------------------------------------------------------ settings
def cfg(profile=None):
    p = profile if isinstance(profile, dict) else (st.session_state.get("user_profile") or {})
    c = dict((p.get("settings") or {}).get("chase") or {})
    return {"on": bool(c.get("on", True)), "wait": int(c.get("wait", 3) or 3)}


def _staff(profile=None):
    import gympulse_automation as ga
    return ga.staff_list(profile)


# ------------------------------------------------------------------ helpers
def _ts(x):
    t = pd.to_datetime(x, errors="coerce", utc=True)
    return None if pd.isna(t) else t


def is_chase(a):
    d = a.get("details")
    return isinstance(d, dict) and isinstance(d.get("chase"), dict)


def chase_rows(sc, gym_id, open_only=True):
    try:
        q = sc.table("retention_actions").select("*").eq("gym_id", gym_id)
        if open_only:
            q = q.neq("status", "Done")
        rows = q.order("created_at", desc=True).limit(1000).execute().data or []
    except Exception:
        return []
    return [r for r in rows if is_chase(r) and gw._blank(r.get("archived_at"))]


def usual_time(ck, member_id):
    """'Usually trains Tuesday evenings' from check-ins, or ''."""
    if ck is None or not len(ck) or "at" not in ck.columns:
        return ""
    mine = ck[ck["member_id"] == member_id]
    if len(mine) < 3:
        return ""
    at = pd.to_datetime(mine["at"], errors="coerce", utc=True).dropna().dt.tz_convert(gw.APP_TZ)
    if at.empty:
        return ""
    day = Counter(at.dt.day_name()).most_common(1)[0][0]
    part = Counter("mornings" if h < 12 else "afternoons" if h < 17 else "evenings" for h in at.dt.hour) \
        .most_common(1)[0][0]
    return f"Usually trains {day} {part}"


def script(first, gym_name, why, kind):
    if kind == "renewal":
        return (f"Hi {first}, it's {{you}} from {gym_name}. Your membership ended a few days ago and we didn't want "
                f"you to lose your progress. Is everything okay? Is there anything stopping you from renewing?")
    return (f"Hi {first}, it's {{you}} from {gym_name}. We haven't seen you in a while and wanted to check you're "
            f"okay. {why + '. ' if why else ''}Is anything making it hard to come in at the moment?")


# ------------------------------------------------------------------ engine (daily job + page open)
def escalate(sc, gym_id, profile=None, gym_name="your gym", dry_run=False, log=print, today=None):
    """Add a call for every automatic message that got no response. Returns how many were added."""
    c = cfg(profile)
    if not c["on"]:
        return 0
    import gympulse_grow as gg
    today = today or gw.today_local()
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=LOOKBACK_DAYS)).isoformat()
    try:
        sent = sc.table("auto_messages").select("*").eq("gym_id", gym_id).eq("status", "sent") \
            .gte("sent_at", start).execute().data or []
    except Exception:
        return 0
    sent = [s for s in sent if s.get("kind") in TRIGGER_KINDS and s.get("member_id")]
    if not sent:
        return 0
    members = gg._members(sc, gym_id)
    if members.empty:
        return 0
    mem = {m["id"]: m for m in members.to_dict("records")}
    ck = gg._checkins(sc, gym_id, 120)
    try:
        acts = sc.table("retention_actions").select("id, member_id, status, details, archived_at") \
            .eq("gym_id", gym_id).execute().data or []
    except Exception:
        return 0
    open_for = {a["member_id"] for a in acts if a.get("status") != "Done" and gw._blank(a.get("archived_at"))}
    done_refs = {(a["member_id"], a["details"]["chase"].get("ref")) for a in acts if is_chase(a)}
    try:
        replies = sc.table("messages").select("member_id, created_at").eq("gym_id", gym_id).eq("direction", "in") \
            .gte("created_at", start).execute().data or []
    except Exception:
        replies = []
    staff, added, rr = _staff(profile), 0, 0
    for s in sorted(sent, key=lambda x: str(x.get("sent_at"))):
        mid, at = s["member_id"], _ts(s.get("sent_at"))
        m = mem.get(mid)
        if m is None or at is None or (mid, s.get("ref")) in done_refs or mid in open_for:
            continue
        if (now - at.to_pydatetime()).days < c["wait"]:
            continue
        if any(r["member_id"] == mid and (_ts(r["created_at"]) or at) > at for r in replies):
            continue                                   # they replied: the inbox handles it
        if len(ck) and ((ck["member_id"] == mid) & (pd.to_datetime(ck["at"], utc=True) > at)).any():
            continue                                   # they came back
        end = m.get("end")
        if s["kind"] == "renewal":
            if not gg._has_date(end) or end > today - timedelta(days=c["wait"]):
                continue                               # renewed, or not lapsed long enough to chase
            why = f"Membership ended {end:%d %b}, not renewed"
        else:
            if gg._has_date(end) and end < today:
                continue                               # lapsed: the renewal chase covers it
            why = f"No reply to \"We missed you\" sent {at.tz_convert(gw.APP_TZ):%d %b}"
        first = gw._text(m.get("full_name"), "there").split()[0]
        details = {"chase": {"ref": s.get("ref"), "kind": s["kind"], "why": why, "tries": 0,
                             "sent_at": s.get("sent_at"), "end": end.isoformat() if gg._has_date(end) else None,
                             "usual": usual_time(ck, mid),
                             "script": script(first, gym_name, "", s["kind"])}}
        if dry_run:
            log(f"  would add a call -> {m.get('full_name')} ({why})")
            added += 1
            continue
        try:
            gw._create_action(sc, gym_id, mid, "Personal call", 0, note=f"Automatic follow-up · {why}.",
                              details=details)
        except Exception as error:
            log(f"  could not add a call for {m.get('full_name')}: {error}")
            continue
        row = gw.open_action_for(sc, mid)
        if row is not None:
            extra = {"created_by": CREATED_BY, "due_date": today.isoformat()}
            if staff:
                extra["assigned_to"] = staff[rr % len(staff)]
                rr += 1
            try:
                sc.table("retention_actions").update(extra).eq("id", row["id"]).execute()
            except Exception:
                pass
        open_for.add(mid)
        added += 1
        log(f"  added a call -> {m.get('full_name')} ({why})")
    return added


def auto_close(sc, gym_id, dry_run=False, log=print):
    """Close calls for members who checked in or renewed after the call was added. Returns how many."""
    rows = chase_rows(sc, gym_id)
    if not rows:
        return 0
    import gympulse_grow as gg
    ck = gg._checkins(sc, gym_id, 120)
    members = gg._members(sc, gym_id)
    ends = {m["id"]: m.get("end") for m in members.to_dict("records")} if not members.empty else {}
    closed = 0
    for a in rows:
        ch, made = a["details"]["chase"], _ts(a.get("created_at"))
        mid = a["member_id"]
        came = None
        if made is not None and len(ck):
            mine = ck[(ck["member_id"] == mid) & (pd.to_datetime(ck["at"], utc=True) > made)]
            if len(mine):
                came = f"Came back: checked in {pd.to_datetime(mine['at'], utc=True).min().tz_convert(gw.APP_TZ):%d %b}"
        end, old = ends.get(mid), ch.get("end")
        if came is None and gg._has_date(end) and old and end.isoformat() > old:
            came = f"Renewed: membership now runs to {end:%d %b %Y}"
        if came is None:
            continue
        if not dry_run:
            try:
                _update(sc, a, {"result": came}, status="Done", outcome="Retained",
                        note=f"{gw._text(a.get('note'))} · {came}.")
            except Exception:
                continue
        log(f"  closed a call ({came})")
        closed += 1
    return closed


def run(sc, gym_id, profile=None, gym_name="your gym", dry_run=False, log=print):
    return escalate(sc, gym_id, profile, gym_name, dry_run, log), auto_close(sc, gym_id, dry_run, log)


# ------------------------------------------------------------------ writes from the Calls screen
def _update(sc, a, chase_patch, status=None, outcome=None, note=None, due=None):
    details = dict(a.get("details") or {})
    details["chase"] = {**dict(details.get("chase") or {}), **chase_patch}
    row = {"details": details}
    if status:
        row["status"] = status
    if outcome:
        row["outcome"] = outcome
        row["completed_at"] = datetime.now(timezone.utc).isoformat()
    if note is not None:
        row["note"] = note
    if due:
        row["due_date"] = due
    sc.table("retention_actions").update(row).eq("id", a["id"]).execute()
    try:
        gw.bump_data_version()
    except Exception:
        pass


def no_answer(sc, a):
    ch = a["details"]["chase"]
    tries = int(ch.get("tries") or 0) + 1
    if tries >= MAX_TRIES:
        _update(sc, a, {"tries": tries, "result": f"No answer after {tries} tries"}, status="Done",
                outcome="No response", note=f"{gw._text(a.get('note'))} · No answer after {tries} tries.")
        return f"No answer {tries} times. Marked as no response."
    nxt = gw.today_local() + timedelta(days=RETRY_DAYS)
    _update(sc, a, {"tries": tries}, status="In progress", due=nxt.isoformat())
    return f"Saved. GymPulse will put this call back on your list on {nxt:%a %d %b}."


def talked(sc, a, reason, coming, said=""):
    label = REASONS[reason][0]
    extra = f" They said: {said.strip()}" if said.strip() else ""
    if coming:
        nxt = gw.today_local() + timedelta(days=7)
        _update(sc, a, {"reason": reason, "said": said.strip(), "talked_at": datetime.now(timezone.utc).isoformat()},
                status="In progress", due=nxt.isoformat(),
                note=f"{gw._text(a.get('note'))} · Talked: {label}. Said they'll come back.{extra}")
        return "Saved. The call closes by itself when they check in or renew."
    _update(sc, a, {"reason": reason, "said": said.strip(), "result": "Not coming back"}, status="Done",
            outcome="Cancelled", note=f"{gw._text(a.get('note'))} · Talked: {label}. Not coming back.{extra}")
    return "Saved. Their reason is counted in Why members stop."


# ------------------------------------------------------------------ owner screen (Follow-ups -> Calls)
def open_count(sc, gym_id):
    return gw._cached(("chase_n", gym_id), lambda: len(chase_rows(sc, gym_id)), ttl=30)


def render_calls(sc, gym_id, gym_name, user_name=""):
    if not st.session_state.get("_chase_ran"):
        st.session_state["_chase_ran"] = True
        try:
            run(sc, gym_id, gym_name=gym_name, log=lambda *_: None)
        except Exception:
            pass
    c = cfg()
    flash = st.session_state.pop("chase_flash", None)
    if flash:
        st.success(flash)
    st.caption(f"When an automatic message gets no reply, check-in or renewal within {c['wait']} days, the member "
               "appears here so a person can call them. Calls close by themselves when the member comes back."
               + ("" if c["on"] else " Automatic follow-up is off: turn it on in Grow → Automatic messages."))
    rows = chase_rows(sc, gym_id)
    today = gw.today_local()
    due = [r for r in rows if str(r.get("due_date") or "")[:10] <= today.isoformat()]
    later = [r for r in rows if r not in due]
    import gympulse_grow as gg
    members = gg._members(sc, gym_id)
    mem = {m["id"]: m for m in members.to_dict("records")} if not members.empty else {}
    if not due:
        st.info("No calls to make today." + (f" {len(later)} coming up." if later else ""))
    for a in due:
        _call_card(sc, a, mem.get(a["member_id"]) or {}, gym_name, user_name)
    if later:
        with st.expander(f"Coming up ({len(later)})", icon=":material/event:"):
            for a in later:
                m = mem.get(a["member_id"]) or {}
                ch = a["details"]["chase"]
                st.markdown(f"**{gw._esc(m.get('full_name') or 'Member')}** · {gw._esc(ch.get('why'))} · "
                            f"back on your list {pd.to_datetime(a['due_date']):%a %d %b}")
    _why_stop(sc, gym_id)


def _call_card(sc, a, m, gym_name, user_name):
    ch = a["details"]["chase"]
    name = gw._text(m.get("full_name"), "Member")
    first = name.split()[0]
    aid = a["id"]
    with st.container(border=True, key=f"chase_{aid}"):
        top = f"**{gw._esc(name)}**"
        bits = [ch.get("why")]
        if ch.get("usual"):
            bits.append(ch["usual"])
        if int(ch.get("tries") or 0):
            bits.append(f"Tried {ch['tries']} time{'s' if int(ch['tries']) > 1 else ''}, no answer")
        if a.get("assigned_to"):
            bits.append(f"For {a['assigned_to']}")
        st.markdown(top)
        st.caption(" · ".join(gw._esc(b) for b in bits if b))
        phone = gw._text(m.get("phone"))
        say = gw._text(ch.get("script")).replace("{you}", user_name.split()[0] if user_name else "the team")
        if phone:
            digits = gw.whatsapp_digits(phone)
            l1, l2 = st.columns(2)
            l1.link_button(f"Call {phone}", f"tel:{phone.replace(' ', '')}", icon=":material/call:",
                           use_container_width=True)
            if digits:
                l2.link_button("WhatsApp", f"https://wa.me/{digits}?text={quote(say)}", icon=":material/chat:",
                               use_container_width=True)
        else:
            st.caption("No phone number saved for this member. Add one in Member Management.")
        with st.expander("What to say", icon=":material/record_voice_over:"):
            st.write(say)
            st.caption("Listen more than you talk. Find out why before offering anything.")
        x, y = st.columns(2)
        if x.button("No answer", key=f"ch_na_{aid}", icon=":material/phone_missed:", use_container_width=True):
            st.session_state["chase_flash"] = no_answer(sc, a)
            st.rerun()
        if y.button("We talked", key=f"ch_t_{aid}", icon=":material/check:", type="primary",
                    use_container_width=True):
            st.session_state[f"ch_open_{aid}"] = True
        if st.session_state.get(f"ch_open_{aid}"):
            reason = st.radio(f"Why did {first} stop coming?", list(REASONS), key=f"ch_r_{aid}",
                              format_func=lambda k: REASONS[k][0], horizontal=True)
            st.info(f"**What to offer:** {REASONS[reason][2]}", icon=":material/lightbulb:")
            said = st.text_input("What they said (optional)", key=f"ch_s_{aid}", max_chars=200)
            p, q = st.columns(2)
            if p.button("Coming back", key=f"ch_y_{aid}", type="primary", use_container_width=True):
                st.session_state["chase_flash"] = talked(sc, a, reason, True, said)
                st.session_state.pop(f"ch_open_{aid}", None)
                st.rerun()
            if q.button("Not coming back", key=f"ch_n_{aid}", use_container_width=True):
                st.session_state["chase_flash"] = talked(sc, a, reason, False, said)
                st.session_state.pop(f"ch_open_{aid}", None)
                st.rerun()


def why_counts(sc, gym_id, days=90):
    since = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
    out = Counter()
    for a in chase_rows(sc, gym_id, open_only=False):
        r = a["details"]["chase"].get("reason")
        t = _ts(a.get("created_at"))
        if r in REASONS and t is not None and t >= since:
            out[r] += 1
    return out


def _why_stop(sc, gym_id):
    cnt = why_counts(sc, gym_id)
    st.markdown('<div class="section-label">WHY MEMBERS STOP · LAST 90 DAYS</div>', unsafe_allow_html=True)
    if not cnt:
        st.caption("When your team records why members stopped, the reasons add up here, so you know what to fix.")
        return
    total = sum(cnt.values())
    for k, n in cnt.most_common():
        st.progress(n / total, text=f"{REASONS[k][0]} · {n} ({round(100 * n / total)}%)")
