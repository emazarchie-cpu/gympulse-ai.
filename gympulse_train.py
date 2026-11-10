"""GymPulse AI · Train: what members use while they're at the gym. Works for one member on their own:
nothing depends on other members posting.

Member app → Train
  * Today: the coach's workout, this week's goal and streak, my workouts (routines), challenges, achievements.
  * Log: pick an exercise (or a routine), see "last time: 60 kg × 8", log sets in two taps. Beating your best
    is a personal record (PR).
  * Progress: records, estimated 1-rep max, a chart per exercise, and a calendar of training days.
  * Body: weight, waist and body fat over time.
  * Gym now: how busy it is right now and the usual pattern for today, from check-ins.
  * Tools: rest timer and plate calculator.
Owner (Train page): today's workout, machine guides with QR codes (public ?guide=<id> page), visit
challenges and training insights.
Database: sql/phase29_train.sql, sql/phase30_train_more.sql (challenges: phase 24 tables).
"""
import io
import uuid
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

SQL_HINT = ("The Train tab needs a one-time setup: open Supabase, go to SQL Editor, paste in the file "
            "sql/phase29_train.sql and press Run.")
EXERCISES = ["Squat", "Bench press", "Deadlift", "Overhead press", "Barbell row", "Romanian deadlift", "Hip thrust",
             "Leg press", "Lunges", "Leg curl", "Leg extension", "Calf raise", "Incline bench press",
             "Dumbbell bench press", "Dumbbell shoulder press", "Chest press machine", "Shoulder press machine",
             "Pec deck", "Lat pulldown", "Seated cable row", "Pull-up", "Chin-up", "Dip", "Push-up",
             "Bicep curl", "Hammer curl", "Tricep pushdown", "Skull crusher", "Lateral raise", "Face pull",
             "Shrug", "Kettlebell swing", "Goblet squat", "Plank", "Crunch", "Cable crunch"]
OTHER = "Other…"
BUCKET = "community"                                  # Supabase storage bucket for guide videos
ACHIEVEMENTS = [  # (key, emoji, title, test)
    ("first", "🎯", "First workout logged", lambda a: a["days"] >= 1),
    ("w10", "💪", "10 workouts", lambda a: a["days"] >= 10),
    ("w25", "🏅", "25 workouts", lambda a: a["days"] >= 25),
    ("w50", "🏆", "50 workouts", lambda a: a["days"] >= 50),
    ("w100", "👑", "100 workouts", lambda a: a["days"] >= 100),
    ("pr1", "⚡", "First PR", lambda a: a["prs"] >= 1),
    ("pr10", "🚀", "10 PRs", lambda a: a["prs"] >= 10),
    ("t1", "🧱", "1 tonne lifted", lambda a: a["volume"] >= 1000),
    ("t10", "🏗️", "10 tonnes lifted", lambda a: a["volume"] >= 10000),
    ("t100", "🦍", "100 tonnes lifted", lambda a: a["volume"] >= 100000),
    ("s4", "🔥", "4-week streak", lambda a: a["streak"] >= 4),
    ("s12", "☄️", "12-week streak", lambda a: a["streak"] >= 12),
    ("goal", "✅", "Hit your weekly goal", lambda a: a["goal_weeks"] >= 1),
    ("body", "📏", "Started tracking your body", lambda a: a["body"] >= 1),
]
PLATES = [25, 20, 15, 10, 5, 2.5, 1.25]


def ready(sc):
    try:
        sc.table("workout_sets").select("id").limit(1).execute()
        return True
    except Exception:
        return False


def e1rm(w, r):
    """Estimated one-rep max (Epley)."""
    w, r = float(w or 0), int(r or 0)
    return round(w * (1 + r / 30), 1) if r > 1 else w


def _fmt(w):
    w = float(w or 0)
    return f"{w:g}"


def _sets(sc, m, exercise=None, days=400):
    since = (gw.today_local() - timedelta(days=days)).isoformat()
    q = sc.table("workout_sets").select("*").eq("member_id", m["id"]).gte("performed_on", since)
    if exercise:
        q = q.eq("exercise", exercise)
    try:
        rows = q.order("performed_on", desc=True).limit(2000).execute().data or []
    except Exception:
        rows = []
    return rows


def best_of(rows):
    """The best set: heaviest weight, then most reps at that weight."""
    if not rows:
        return None
    return max(rows, key=lambda r: (float(r["weight_kg"]), int(r["reps"])))


def is_pr(prev_rows, w, r):
    b = best_of(prev_rows)
    if b is None:
        return False                                  # first time: nothing to beat yet
    return float(w) > float(b["weight_kg"]) or (float(w) == float(b["weight_kg"]) and int(r) > int(b["reps"]))


# ------------------------------------------------------------------ member: Train tab
def render_member(sc, m, gym_name, prof):
    if not ready(sc):
        st.info("Training tools are coming soon to this gym.")
        return
    st.markdown(CSS, unsafe_allow_html=True)
    views = ["Today", "Log", "Progress", "Body", "Gym now", "Tools"]
    if st.session_state.get("tr_view") not in views:
        st.session_state["tr_view"] = "Today"
    view = st.segmented_control("Train", views, key="tr_view", label_visibility="collapsed") or "Today"
    if view == "Today":
        _home(sc, m, gym_name)
    elif view == "Log":
        _log(sc, m, gym_name)
    elif view == "Progress":
        _progress(sc, m)
    elif view == "Body":
        _body(sc, m)
    elif view == "Gym now":
        _busy(sc, m, prof)
    else:
        _tools()


CSS = """<style>
.tr-ring { display:flex; align-items:center; gap:16px; }
.tr-ring svg { flex:0 0 auto; }
.tr-big { font-size:26px; font-weight:900; line-height:1.1; }
.tr-sub { color:#93A0B4; font-size:14px; }
.tr-ach { display:grid; grid-template-columns:repeat(auto-fill,minmax(96px,1fr)); gap:8px; }
.tr-ach div { border-radius:14px; padding:10px 6px; text-align:center; background:rgba(255,255,255,.05);
              border:1px solid rgba(255,255,255,.08); font-size:12px; font-weight:700; line-height:1.3; }
.tr-ach div b { display:block; font-size:24px; }
.tr-ach .off { opacity:.35; filter:grayscale(1); }
.tr-cal { display:grid; grid-template-columns:repeat(7,1fr); gap:4px; }
.tr-cal i { aspect-ratio:1; border-radius:6px; background:rgba(255,255,255,.06); display:block; }
.tr-cal i.on { background:linear-gradient(135deg,#B7F34A,#35D3E8); }
.tr-cal i.gym { background:rgba(53,211,232,.35); }
.tr-cal i.today { outline:2px solid #F4F7FB; }
</style>"""


def _coach_card(sc, m):
    today = gw.today_local()
    try:
        rows = sc.table("coach_workouts").select("*").eq("gym_id", m["gym_id"]) \
            .gte("day", (today - timedelta(days=1)).isoformat()).lte("day", today.isoformat()) \
            .order("day", desc=True).limit(1).execute().data or []
    except Exception:
        rows = []
    if not rows:
        return
    w = rows[0]
    when = "Today" if str(w["day"]) == today.isoformat() else "Yesterday"
    with st.container(border=True, key="tr_coach"):
        gw._md(f'<div style="font-size:12px;font-weight:800;letter-spacing:.08em;color:#B7F34A">{when.upper()}\'S '
               f'WORKOUT{" · " + gw._esc(w.get("author")) if w.get("author") else ""}</div>'
               f'<div style="font-size:18px;font-weight:800;margin:4px 0 6px">{gw._esc(w["title"])}</div>'
               f'<div style="white-space:pre-wrap;line-height:1.5">{gw._esc(w["body"])}</div>')
        found = [e for e in EXERCISES if e.lower() in w["body"].lower()][:6]
        if found:
            st.caption("Tap an exercise to log it")
            cols = st.columns(min(3, len(found)))
            for i, e in enumerate(found):
                cols[i % len(cols)].button(e, key=f"tr_wod_{i}", on_click=_pick, args=(e,), use_container_width=True)


def _pick(ex):
    st.session_state["tr_ex"] = ex
    st.session_state["tr_view"] = "Log"


def _log(sc, m, gym_name):
    flash = st.session_state.pop("tr_flash", None)
    if flash:
        if flash[0] == "pr":
            st.toast(flash[1], icon="🏆")
            gw._md(f'<div class="mp-card" style="border-color:rgba(183,243,74,.5)"><div style="font-size:13px;'
                   f'color:#B7F34A;font-weight:800;letter-spacing:.08em">PERSONAL RECORD</div>'
                   f'<div style="font-size:22px;font-weight:900">{gw._esc(flash[1])}</div></div>')
        else:
            (st.success if flash[0] == "ok" else st.info)(flash[1])
    _routine_bar(sc, m)
    rows = _sets(sc, m)
    mine = []
    for r in rows:
        if r["exercise"] not in mine:
            mine.append(r["exercise"])
    options = mine[:8] + [e for e in EXERCISES if e not in mine[:8]] + [OTHER]
    if st.session_state.get("tr_ex") not in options:
        st.session_state["tr_ex"] = options[0]
    ex = st.selectbox("Exercise", options, key="tr_ex")
    if ex == OTHER:
        ex = st.text_input("Exercise name", max_chars=60, key="tr_other").strip().capitalize()
        if not ex:
            return
    today = gw.today_local().isoformat()
    hist = [r for r in rows if r["exercise"] == ex]
    done = [r for r in hist if str(r["performed_on"]) == today]
    before = [r for r in hist if str(r["performed_on"]) != today]
    last_day = before[0]["performed_on"] if before else None
    last = sorted([r for r in before if r["performed_on"] == last_day], key=lambda r: r["created_at"]) if last_day else []
    best = best_of(before)
    bits = []
    if last:
        d = pd.Timestamp(str(last_day))
        bits.append(f"**Last time** ({d:%a %d %b}): " + ", ".join(f"{_fmt(r['weight_kg'])} kg × {r['reps']}" for r in last))
    best_all = best_of(before + done)
    if best_all:
        bits.append(f"**Best**: {_fmt(best_all['weight_kg'])} kg × {best_all['reps']}")
    if bits:
        st.markdown(" · ".join(bits))
    elif not done:
        st.caption("First time logging this one. Your numbers will show here next time.")
    seed = (done[-1] if done else (last[0] if last else None))
    w0 = float(seed["weight_kg"]) if seed else 20.0
    r0 = int(seed["reps"]) if seed else 8
    c1, c2 = st.columns(2)
    w = c1.number_input("Weight (kg)", min_value=0.0, max_value=999.0, value=w0, step=2.5, key=f"tr_w_{ex}")
    r = c2.number_input("Reps", min_value=1, max_value=200, value=r0, step=1, key=f"tr_r_{ex}")
    if st.button(f"Add set {len(done) + 1}", type="primary", icon=":material/add:", key="tr_add",
                 use_container_width=True):
        try:
            sc.table("workout_sets").insert({"gym_id": m["gym_id"], "member_id": m["id"], "exercise": ex[:60],
                                             "weight_kg": float(w), "reps": int(r), "performed_on": today}).execute()
        except Exception:
            st.error("That set couldn't be saved. Please try again.")
            return
        prev = before + done
        if is_pr(prev, w, r):
            st.session_state["tr_flash"] = ("pr", f"New PR: {ex} {_fmt(w)} kg × {int(r)} 🎉")
        else:
            st.session_state["tr_flash"] = ("ok", f"Set {len(done) + 1} saved: {_fmt(w)} kg × {int(r)}")
        st.rerun()
    _today(sc, m, [r for r in rows if str(r["performed_on"]) == today])


def _today(sc, m, rows):
    if not rows:
        return
    rows = sorted(rows, key=lambda r: r["created_at"])
    vol = sum(float(r["weight_kg"]) * int(r["reps"]) for r in rows)
    st.markdown(f'<div class="section-label">TODAY · {len(rows)} SET{"S" if len(rows) != 1 else ""} · '
                f'{vol:,.0f} KG LIFTED</div>', unsafe_allow_html=True)
    by = {}
    for r in rows:
        by.setdefault(r["exercise"], []).append(r)
    for ex, sets in by.items():
        with st.container(border=True, key=f"tr_day_{ex}"):
            st.markdown(f"**{ex}**")
            for i, s in enumerate(sets, 1):
                a, b = st.columns([5, 1], vertical_alignment="center")
                a.write(f"Set {i}: {_fmt(s['weight_kg'])} kg × {s['reps']}")
                if b.button("✕", key=f"tr_del_{s['id']}", help="Delete this set"):
                    sc.table("workout_sets").delete().eq("id", s["id"]).eq("member_id", m["id"]).execute()
                    st.rerun()


def _progress(sc, m):
    rows = _sets(sc, m)
    if not rows:
        st.info("Log a few sets and your records and progress will show here.")
        return
    df = pd.DataFrame(rows)
    df["weight_kg"] = df["weight_kg"].astype(float)
    df["e1rm"] = [e1rm(w, r) for w, r in zip(df["weight_kg"], df["reps"])]
    days = df["performed_on"].nunique()
    week_start = gw.today_local() - timedelta(days=gw.today_local().weekday())
    this_week = df[pd.to_datetime(df["performed_on"]).dt.date >= week_start]["performed_on"].nunique()
    gw.kpi_row([("Workouts logged", str(days), "cyan", "days with sets"),
                ("This week", str(this_week), "lime", "workouts"),
                ("Exercises", str(df["exercise"].nunique()), "amber", "tracked")])
    _calendar(sc, m, rows)
    st.markdown('<div class="section-label">PERSONAL RECORDS</div>', unsafe_allow_html=True)
    recs = []
    for ex, g in df.groupby("exercise"):
        b = best_of(g.to_dict("records"))
        recs.append({"Exercise": ex, "Best": f"{_fmt(b['weight_kg'])} kg × {b['reps']}",
                     "Est. 1-rep max": f"{g['e1rm'].max():g} kg", "When": pd.Timestamp(str(b["performed_on"])).strftime("%d %b"),
                     "_n": len(g)})
    recs.sort(key=lambda x: -x["_n"])
    gw.table([{k: v for k, v in r.items() if k != "_n"} for r in recs], max_height=360)
    ex = st.selectbox("See progress for", [r["Exercise"] for r in recs], key="tr_prog_ex")
    g = df[df["exercise"] == ex].groupby("performed_on").agg(top=("weight_kg", "max"), best=("e1rm", "max")).reset_index()
    g["day"] = pd.to_datetime(g["performed_on"])
    if len(g) < 2:
        st.caption("Log this exercise on another day to see your progress line.")
        return
    try:
        import altair as alt
        base = alt.Chart(g).encode(x=alt.X("day:T", title=None, axis=alt.Axis(format="%d %b", labelColor="#93A0B4")))
        line = base.mark_line(color="#B7F34A", strokeWidth=3, point=alt.OverlayMarkDef(color="#B7F34A", size=60)) \
            .encode(y=alt.Y("top:Q", title="Top set (kg)", axis=alt.Axis(labelColor="#93A0B4", titleColor="#93A0B4")),
                    tooltip=[alt.Tooltip("day:T", title="Day", format="%a %d %b"), alt.Tooltip("top:Q", title="Top set kg"),
                             alt.Tooltip("best:Q", title="Est. 1-rep max")])
        st.altair_chart(line.properties(height=240).configure(background="rgba(0,0,0,0)")
                        .configure_view(strokeWidth=0).configure_axis(gridColor="rgba(255,255,255,0.07)"),
                        use_container_width=True)
    except Exception:
        st.line_chart(g.set_index("day")["top"])
    first, last = g.iloc[0], g.iloc[-1]
    diff = float(last["top"]) - float(first["top"])
    if diff > 0:
        st.success(f"Up {diff:g} kg on {ex} since {first['day']:%d %b} 💪")


DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]   # Postgres dow order
DEFAULT_VISIT = 75


GROUPS = {"wk": "Monday to Friday", "sat": "Saturday", "sun": "Sunday"}
OPEN_TIMES = list(range(0, 1440, 5))                  # minutes after midnight, every 5 minutes
CLOSE_TIMES = list(range(5, 1441, 5))                 # 1440 = midnight


def _group(dow):
    return "sun" if dow == 0 else "sat" if dow == 6 else "wk"


def traffic_cfg(profile):
    """{"visit": minutes, "hours": None or {"wk"|"sat"|"sun": [open_min, close_min] or None (closed)}}.
    Times are minutes after midnight; a close of 1440 is midnight."""
    c = dict(((profile or {}).get("settings") or {}).get("traffic") or {})
    hours = c.get("hours")
    if not hours and c.get("open") is not None and c.get("close") is not None:     # older whole-hour setting
        span = [int(c["open"]) * 60, int(c["close"]) * 60]
        hours = {"wk": span, "sat": span, "sun": span}
    return {"visit": int(c.get("visit") or DEFAULT_VISIT), "hours": hours or None}


def hours_for(cfg, dow):
    """(open_min, close_min) for that weekday, None if closed, or False if the owner hasn't set hours."""
    if not cfg.get("hours"):
        return False
    h = cfg["hours"].get(_group(dow))
    return tuple(h) if h else None


def clock(minutes):
    h, m = divmod(int(minutes) % 1440, 60)
    return f"{h % 12 or 12}{f':{m:02d}' if m else ''}{'am' if h < 12 else 'pm'}"


def _slot_label(slot, end=False):
    h, mnt = divmod(int(slot) * 30 + (30 if end else 0), 60)
    h %= 24
    return f"{h % 12 or 12}{':30' if mnt else ''}{'am' if h < 12 else 'pm'}"


def traffic(sc, gym_id, visit):
    """{dow: {"days": n, "slots": {slot: avg people}}} from gp_gym_traffic, or None before phase 31."""
    def load():
        try:
            rows = sc.rpc("gp_gym_traffic", {"p_gym": gym_id, "p_minutes": int(visit)}).execute().data or []
        except Exception:
            return None
        out = {}
        for r in rows:
            d = out.setdefault(int(r["dow"]), {"days": int(r["days"]), "slots": {}})
            d["slots"][int(r["slot"])] = float(r["avg_people"])
        return out
    return gw._cached(("traffic", gym_id, int(visit)), load, ttl=600)


def inside_now(sc, gym_id, visit):
    """People who checked in within the last visit length (each member once)."""
    since = (datetime.now(timezone.utc) - timedelta(minutes=int(visit))).isoformat()
    try:
        rows = sc.table("checkins").select("member_id").eq("gym_id", gym_id).gte("checked_in_at", since) \
            .limit(5000).execute().data or []
        return len({r["member_id"] for r in rows if r.get("member_id")})
    except Exception:
        return None


def open_slots(day, cfg, dow=None):
    """Half hours the gym is open on that weekday: any half hour that overlaps the owner's opening hours
    (5:30–10:45pm keeps the 10:30 slot), else every half hour that had people in it."""
    h = hours_for(cfg, dow) if dow is not None else False
    if h is None:
        return []
    if h:
        o, c = h
        return [x for x in range(48) if x * 30 < c and x * 30 + 30 > o]
    return sorted(s for s, v in day["slots"].items() if v > 0)


def slot_range(x, cfg, dow):
    """'5:30am–6am', trimmed to opening hours (opens 5:45 -> '5:45am–6am')."""
    a, b = x * 30, x * 30 + 30
    h = hours_for(cfg, dow)
    if h:
        a, b = max(a, h[0]), min(b, h[1])
    return f"{clock(a)}–{clock(b)}"


def level(now_n, peak):
    if peak <= 0:
        return ("Quiet", "#B7F34A") if now_n <= 2 else ("Busy", "#FF6B6B")
    r = now_n / peak
    if r < 0.4:
        return "Quiet", "#B7F34A"
    if r < 0.75:
        return "Moderate", "#FFC44D"
    return "Busy", "#FF6B6B"


def _busy(sc, m, profile=None):
    cfg = traffic_cfg(profile or st.session_state.get("_tr_prof"))
    data = traffic(sc, m["gym_id"], cfg["visit"])
    if data is None:
        st.info("Gym busyness will show here soon.")
        return
    render_traffic(data, inside_now(sc, m["gym_id"], cfg["visit"]), cfg, key="tr_tf")


# Typical busyness of a Lagos gym (0–1 per half hour), used until a gym has enough of its own check-ins:
# weekdays peak before work and after work, quiet late morning to mid afternoon; Saturdays peak mid morning;
# Sundays are lighter. Keys are "H:MM".
_TYPICAL = {
    "wk": {"5:00": .25, "5:30": .5, "6:00": .8, "6:30": .95, "7:00": .9, "7:30": .7, "8:00": .5, "8:30": .35,
           "9:00": .25, "9:30": .2, "10:00": .17, "10:30": .15, "11:00": .15, "11:30": .18, "12:00": .25,
           "12:30": .3, "13:00": .28, "13:30": .2, "14:00": .13, "14:30": .12, "15:00": .12, "15:30": .15,
           "16:00": .25, "16:30": .45, "17:00": .7, "17:30": .9, "18:00": 1, "18:30": 1, "19:00": .9,
           "19:30": .75, "20:00": .55, "20:30": .4, "21:00": .25, "21:30": .15, "22:00": .08, "22:30": .05},
    "sat": {"6:00": .2, "6:30": .35, "7:00": .55, "7:30": .7, "8:00": .85, "8:30": .95, "9:00": 1, "9:30": 1,
            "10:00": .9, "10:30": .8, "11:00": .65, "11:30": .55, "12:00": .45, "12:30": .38, "13:00": .3,
            "13:30": .25, "14:00": .22, "14:30": .22, "15:00": .25, "15:30": .3, "16:00": .35, "16:30": .4,
            "17:00": .42, "17:30": .4, "18:00": .35, "18:30": .28, "19:00": .2, "19:30": .12, "20:00": .08},
    "sun": {"7:00": .25, "7:30": .35, "8:00": .45, "8:30": .55, "9:00": .6, "9:30": .6, "10:00": .55,
            "10:30": .45, "11:00": .35, "11:30": .3, "12:00": .25, "12:30": .2, "13:00": .15, "13:30": .15,
            "14:00": .15, "14:30": .18, "15:00": .22, "15:30": .3, "16:00": .38, "16:30": .45, "17:00": .52,
            "17:30": .55, "18:00": .55, "18:30": .5, "19:00": .42, "19:30": .32, "20:00": .2, "20:30": .1},
}
TYPICAL = {g: {int(k.split(":")[0]) * 2 + int(k.split(":")[1]) // 30: v for k, v in d.items()}
           for g, d in _TYPICAL.items()}


def busyness(day, dow, cfg):
    """(slots, {slot: 0–1 busyness}, weight of own data 0–1, peak people in own data).
    Own check-ins take over from the typical pattern as days and visitors build up."""
    typical = TYPICAL[_group(dow)]
    own = day.get("slots") or {}
    peak = max(own.values(), default=0)
    days = int(day.get("days") or 0)
    w = (days / (days + 3)) * min(1.0, peak / 5) if peak else 0.0
    h = hours_for(cfg, dow)
    if h is None:
        return [], {}, w, peak
    if h:
        slots = [x for x in range(48) if x * 30 < h[1] and x * 30 + 30 > h[0]]
    else:
        extra = {x for x, v in own.items() if peak and v / peak >= 0.15 and days >= 3}   # e.g. a 24-hour gym
        slots = sorted(set(typical) | extra)
    out = {}
    for x in slots:
        mine = own.get(x, 0) / peak if peak else 0
        out[x] = w * mine + (1 - w) * typical.get(x, 0.05)
    return slots, out, w, peak


def _lvl(b):
    return ("Quiet", "#B7F34A") if b < 0.35 else ("Moderate", "#FFC44D") if b < 0.7 else ("Busy", "#FF6B6B")


def render_traffic(data, now_n, cfg, key):
    nowt = datetime.now(gw.APP_TZ)
    dow = (nowt.weekday() + 1) % 7
    slot = nowt.hour * 2 + nowt.minute // 30
    today = data.get(dow) or {"days": 0, "slots": {}}
    slots, busy, w, peak = busyness(today, dow, cfg)
    h = hours_for(cfg, dow)
    mins = nowt.hour * 60 + nowt.minute
    if h is None:
        closed = True
    elif h:
        closed = not (h[0] <= mins < h[1])
    else:
        closed = not slots or slot < slots[0] or slot > slots[-1]
    usual_b = busy.get(slot, 0)
    reliable = w >= 0.5 and peak >= 3
    if closed:
        lvl, tone = "Closed", "#93A0B4"
    elif reliable:                                   # enough data: judge by the people inside right now
        lvl, tone = _lvl((now_n or 0) / peak)
    else:                                            # not enough data yet: the usual for this time
        lvl, tone = _lvl(usual_b)
    hrs = ("Closed today" if h is None else f"Open {clock(h[0])}–{clock(h[1])} today" if h else "")
    n = now_n or 0
    live = (f"{n} {'person' if n == 1 else 'people'} checked in during the last {cfg['visit']} minutes"
            if n else f"No check-ins in the last {cfg['visit']} minutes")
    sub = ""
    if not closed:
        sub = (f"Usually about {today['slots'].get(slot, 0):.0f} people at this time on {DAYS[dow]}s"
               if reliable else f"Usually {_lvl(usual_b)[0].lower()} at this time on {DAYS[dow]}s")
    gw._md(f'<div class="mp-card"><div style="font-size:13px;color:#93A0B4">Right now · {nowt:%I:%M %p}'
           f'{" · " + hrs if hrs else ""}</div>'
           f'<div style="font-size:30px;font-weight:900;color:{tone}">{lvl}</div>'
           f'<div style="font-size:16px;font-weight:700">{live}</div>'
           + (f'<div class="tr-sub">{sub}</div>' if sub else "") + '</div>')
    ahead = [x for x in slots if x > slot]
    if ahead and not (h is None):
        q = min(ahead, key=lambda x: (busy[x], x))
        st.markdown(f"**Quietest later today:** {slot_range(q, cfg, dow)} · usually {_lvl(busy[q])[0].lower()}")
    order = [(dow + i) % 7 for i in range(7)]
    pick = st.segmented_control("Day", order, default=dow, key=f"{key}_day", label_visibility="collapsed",
                                format_func=lambda d: "Today" if d == dow else DAYS[d][:3]) or dow
    day = data.get(pick) or {"days": 0, "slots": {}}
    ph = hours_for(cfg, pick)
    if ph is None:
        st.info(f"Closed on {DAYS[pick]}s.")
        return
    pslots, pbusy, pw, ppeak = busyness(day, pick, cfg)
    if ph:
        st.caption(f"Open {clock(ph[0])}–{clock(ph[1])} on {DAYS[pick]}s.")
    if not pslots:
        st.info(f"No opening hours on {DAYS[pick]}s.")
        return
    preliable = pw >= 0.5 and ppeak >= 3
    df = pd.DataFrame([{"slot": x, "busy": round(pbusy[x] * 100), "time": _slot_label(x),
                        "range": slot_range(x, cfg, pick), "level": _lvl(pbusy[x])[0],
                        "people": round(day["slots"].get(x, 0)) if preliable else None,
                        "kind": "Now" if (pick == dow and x == slot) else _lvl(pbusy[x])[0]} for x in pslots])
    try:
        import altair as alt
        tips = [alt.Tooltip("range:N", title="Time"), alt.Tooltip("level:N", title="Usually")]
        if preliable:
            tips.append(alt.Tooltip("people:Q", title="People inside"))
        chart = alt.Chart(df).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
            x=alt.X("time:N", sort=list(df["time"]), title=None,
                    axis=alt.Axis(labelColor="#93A0B4", labelAngle=0, labelOverlap=True)),
            y=alt.Y("busy:Q", title=None, scale=alt.Scale(domain=[0, 100]), axis=None),
            color=alt.Color("kind:N", legend=None, scale=alt.Scale(
                domain=["Now", "Busy", "Moderate", "Quiet"], range=["#F4F7FB", "#FF6B6B", "#FFC44D", "#5B7A3A"])),
            tooltip=tips)
        st.markdown(f"**Usually on {DAYS[pick]}s**")
        st.altair_chart(chart.properties(height=190).configure(background="rgba(0,0,0,0)")
                        .configure_view(strokeWidth=0), use_container_width=True)
    except Exception:
        st.bar_chart(df.set_index("time")["busy"])
    gw._md('<div class="tr-sub" style="display:flex;gap:14px;flex-wrap:wrap">'
           '<span>🟥 Busy</span><span>🟨 Moderate</span><span>🟩 Quiet</span>'
           + ('<span>⬜ Now</span>' if pick == dow else '') + '</div>')
    busiest = max(pslots, key=lambda x: pbusy[x])
    quiet = [x for x in pslots if pbusy[x] < 0.35]
    st.caption(f"Busiest around {slot_range(busiest, cfg, pick)}"
               + (f" · quiet from {clock(quiet[0] * 30)}" if quiet else "") + ".")
    nd = int(day.get("days") or 0)
    if pw < 0.5:
        st.caption(f"Based on typical Lagos gym times for now, plus {nd} {DAYS[pick]}{'s' if nd != 1 else ''} of "
                   "your gym's check-ins. It switches to your gym's own pattern as more members check in.")
    else:
        st.caption(f"Based on {nd} {DAYS[pick]}s of your gym's check-ins in the last 8 weeks. "
                   f"Each visit counts as about {cfg['visit']} minutes.")


def plates_for(target, bar=20.0):
    """Plates per side for a target weight, from the usual plate set. Returns (plates, leftover kg)."""
    per_side = max(0.0, (float(target) - float(bar)) / 2)
    out = []
    for p in PLATES:
        while per_side >= p - 1e-9:
            out.append(p)
            per_side -= p
    return out, round(per_side * 2, 2)


def _tools():
    st.markdown("**Rest timer**")
    import streamlit.components.v1 as components
    components.html(TIMER_HTML, height=190)
    st.markdown("**Plate calculator**")
    c1, c2 = st.columns(2)
    target = c1.number_input("Total weight (kg)", 0.0, 500.0, 60.0, 2.5, key="tr_plate_t")
    bar = c2.selectbox("Bar", [20.0, 15.0, 10.0], format_func=lambda b: f"{b:g} kg bar", key="tr_plate_b")
    if target < bar:
        st.caption("That's less than the bar on its own.")
        return
    plates, left = plates_for(target, bar)
    side = " + ".join(f"{p:g}" for p in plates) or "no plates"
    gw._md(f'<div class="mp-card"><div style="font-size:13px;color:#93A0B4">On each side</div>'
           f'<div style="font-size:22px;font-weight:900">{side}</div>'
           + (f'<div style="color:#FFC44D">{left:g} kg can\'t be made with standard plates.</div>' if left else "")
           + '</div>')


TIMER_HTML = """
<div id="t" style="font-family:Inter,system-ui,sans-serif;color:#F4F7FB;text-align:center">
  <div id="v" style="font-size:52px;font-weight:900;letter-spacing:-1px">1:30</div>
  <div style="display:flex;gap:8px;justify-content:center;margin:8px 0">
    <button data-s="60">1:00</button><button data-s="90">1:30</button><button data-s="120">2:00</button><button data-s="180">3:00</button>
  </div>
  <button id="go" style="background:linear-gradient(135deg,#B7F34A,#35D3E8);color:#0A0F1E;width:70%">Start</button>
</div>
<style>button{border:none;border-radius:12px;padding:10px 14px;font-weight:800;font-size:15px;
background:rgba(255,255,255,.08);color:#F4F7FB;cursor:pointer} body{margin:0;background:transparent}</style>
<script>
let total=90,left=90,timer=null;const v=document.getElementById('v'),go=document.getElementById('go');
const show=()=>{v.textContent=Math.floor(left/60)+':'+String(left%60).padStart(2,'0');v.style.color=left<=10&&timer?'#FF6B6B':'#F4F7FB'};
function beep(){try{const a=new (window.AudioContext||window.webkitAudioContext)(),o=a.createOscillator();o.connect(a.destination);
o.frequency.value=880;o.start();setTimeout(()=>{o.stop();a.close()},400)}catch(e){}if(navigator.vibrate)navigator.vibrate([300,100,300]);}
function stop(){clearInterval(timer);timer=null;go.textContent='Start'}
document.querySelectorAll('[data-s]').forEach(b=>b.onclick=()=>{stop();total=left=+b.dataset.s;show()});
go.onclick=()=>{if(timer){stop();return}if(left<=0)left=total;go.textContent='Stop';
timer=setInterval(()=>{left--;show();if(left<=0){stop();beep();left=total;v.textContent='Go! 💪'}},1000)};show();
</script>
"""


# ------------------------------------------------------------------ member: training days, goal, streak
def training_days(sc, m, rows=None, days=200):
    """Dates the member trained: logged sets or a gym check-in."""
    rows = rows if rows is not None else _sets(sc, m, days=days)
    logged = {pd.Timestamp(str(r["performed_on"])).date() for r in rows}
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        cks = sc.table("checkins").select("checked_in_at").eq("member_id", m["id"]).gte("checked_in_at", since) \
            .limit(2000).execute().data or []
    except Exception:
        cks = []
    gym = {pd.to_datetime(c["checked_in_at"], utc=True).tz_convert(gw.APP_TZ).date() for c in cks
           if c.get("checked_in_at")}
    return logged, gym


def week_streak(days, goal=1, today=None):
    """Weeks in a row (Mon–Sun) with at least `goal` training days. This week counts once it's reached."""
    today = today or gw.today_local()
    wk = today - timedelta(days=today.weekday())
    per = {}
    for d in days:
        k = d - timedelta(days=d.weekday())
        per[k] = per.get(k, 0) + 1
    n = 0
    if per.get(wk, 0) >= goal:
        n = 1
    w = wk - timedelta(days=7)
    while per.get(w, 0) >= goal:
        n += 1
        w -= timedelta(days=7)
    return n, per.get(wk, 0), sum(1 for k, v in per.items() if v >= goal and k < wk)


def _ring(done, goal, size=86):
    pct = min(1.0, done / max(goal, 1))
    r, c = 34, 2 * 3.14159 * 34
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 86 86"><circle cx="43" cy="43" r="{r}" fill="none" '
            f'stroke="rgba(255,255,255,.08)" stroke-width="10"/><circle cx="43" cy="43" r="{r}" fill="none" '
            f'stroke="#B7F34A" stroke-width="10" stroke-linecap="round" stroke-dasharray="{c * pct:.1f} {c:.1f}" '
            f'transform="rotate(-90 43 43)"/><text x="43" y="50" text-anchor="middle" font-size="20" font-weight="900" '
            f'fill="#F4F7FB" font-family="Inter,sans-serif">{done}/{goal}</text></svg>')


def _home(sc, m, gym_name):
    flash = st.session_state.pop("tr_home_flash", None)
    if flash:
        st.success(flash)
    _coach_card(sc, m)
    rows = _sets(sc, m)
    logged, gym = training_days(sc, m, rows)
    days = logged | gym
    goal = int(m.get("train_week_goal") or 3)
    streak, this_week, _ = week_streak(days, goal)
    left = max(0, goal - this_week)
    msg = ("Goal reached this week 🎉" if not left else
           f"{left} more workout{'s' if left != 1 else ''} to hit your goal this week")
    with st.container(border=True, key="tr_goal"):
        gw._md(f'<div class="tr-ring">{_ring(this_week, goal)}<div><div class="tr-big">'
               f'{"🔥 " + str(streak) + "-week streak" if streak else "This week"}</div>'
               f'<div class="tr-sub">{msg}. Gym check-ins count too.</div></div></div>')
        with st.popover("Change my weekly goal", use_container_width=True):
            g = st.select_slider("Workouts a week", options=list(range(1, 8)), value=goal, key="tr_goal_pick")
            if st.button("Save goal", key="tr_goal_save", type="primary"):
                try:
                    sc.table("members").update({"train_week_goal": int(g)}).eq("id", m["id"]).execute()
                    m["train_week_goal"] = int(g)
                    st.session_state["tr_home_flash"] = f"Goal set: {g} workout{'s' if g != 1 else ''} a week."
                except Exception:
                    st.session_state["tr_home_flash"] = "Goals need a quick update from your gym."
                st.rerun()
    _routines(sc, m, rows)
    _challenges(sc, m, gym)
    st.markdown('<div class="section-label">ACHIEVEMENTS</div>', unsafe_allow_html=True)
    _achievements(sc, m, rows, days, goal)


# ------------------------------------------------------------------ member: routines
def _my_routines(sc, m):
    try:
        return sc.table("workout_routines").select("*").eq("member_id", m["id"]).order("created_at", desc=True) \
            .limit(20).execute().data or []
    except Exception:
        return None


def _start(name, exercises):
    exercises = [e for e in exercises if e]
    if not exercises:
        return
    st.session_state["tr_routine"] = {"name": name, "exercises": exercises}
    st.session_state["tr_ex"] = exercises[0]
    st.session_state["tr_view"] = "Log"


def _routines(sc, m, rows):
    st.markdown('<div class="section-label">MY WORKOUTS</div>', unsafe_allow_html=True)
    saved = _my_routines(sc, m)
    days = sorted({str(r["performed_on"]) for r in rows}, reverse=True)
    last_day = days[0] if days else None
    last_ex = []
    for r in sorted([r for r in rows if str(r["performed_on"]) == last_day], key=lambda r: r["created_at"]):
        if r["exercise"] not in last_ex:
            last_ex.append(r["exercise"])
    if last_ex:
        st.button(f"Repeat last workout ({pd.Timestamp(last_day):%a %d %b}): {', '.join(last_ex[:3])}"
                  + ("…" if len(last_ex) > 3 else ""), key="tr_repeat", icon=":material/replay:", type="primary",
                  use_container_width=True, on_click=_start, args=("Last workout", last_ex))
    if saved is None:
        return
    for rt in saved:
        a, b = st.columns([5, 1], vertical_alignment="center")
        a.button(f"{rt['name']} · {len(rt['exercises'])} exercises", key=f"tr_rt_{rt['id']}",
                 icon=":material/play_arrow:", use_container_width=True, on_click=_start,
                 args=(rt["name"], rt["exercises"]))
        if b.button("✕", key=f"tr_rtdel_{rt['id']}", help="Delete this workout"):
            sc.table("workout_routines").delete().eq("id", rt["id"]).eq("member_id", m["id"]).execute()
            st.rerun()
    with st.expander("Create a workout", icon=":material/add:"):
        with st.form("tr_rt_new", clear_on_submit=True):
            name = st.text_input("Name", max_chars=60, placeholder="e.g. Push day, Leg day")
            mine = list(dict.fromkeys(r["exercise"] for r in rows))
            picks = st.multiselect("Exercises, in order", list(dict.fromkeys(mine + EXERCISES)), max_selections=12)
            if st.form_submit_button("Save workout", type="primary"):
                if not name.strip() or not picks:
                    st.error("Give it a name and pick at least one exercise.")
                else:
                    sc.table("workout_routines").insert({"gym_id": m["gym_id"], "member_id": m["id"],
                                                         "name": name.strip(), "exercises": picks}).execute()
                    st.session_state["tr_home_flash"] = f"Saved: {name.strip()}. Tap it to start."
                    st.rerun()


def _routine_bar(sc, m):
    rt = st.session_state.get("tr_routine")
    if not rt:
        return
    today = gw.today_local().isoformat()
    try:
        done = {r["exercise"] for r in sc.table("workout_sets").select("exercise").eq("member_id", m["id"])
                .eq("performed_on", today).execute().data or []}
    except Exception:
        done = set()
    n = sum(1 for e in rt["exercises"] if e in done)
    with st.container(border=True, key="tr_rt_bar"):
        st.markdown(f"**{rt['name']}** · {n} of {len(rt['exercises'])} done")
        st.progress(n / len(rt["exercises"]))
        cols = st.columns(min(3, len(rt["exercises"])))
        for i, e in enumerate(rt["exercises"]):
            cols[i % len(cols)].button(("✓ " if e in done else "") + e, key=f"tr_rtx_{i}", on_click=_pick, args=(e,),
                                       use_container_width=True, type="primary" if e == st.session_state.get("tr_ex") else "secondary")
        if st.button("Finish workout" if n else "Close", key="tr_rt_end", type="tertiary"):
            st.session_state.pop("tr_routine", None)
            if n:
                st.session_state["tr_home_flash"] = f"Workout done: {n} exercise{'s' if n != 1 else ''} 💪"
                st.session_state["tr_view"] = "Today"
            st.rerun()


# ------------------------------------------------------------------ member: achievements
def achievement_stats(rows, days, goal, body_n, today=None):
    df = sorted(rows, key=lambda r: (str(r["performed_on"]), str(r.get("created_at"))))
    best, prs = {}, 0
    for r in df:
        k = r["exercise"]
        w, n = float(r["weight_kg"]), int(r["reps"])
        if k in best and (w > best[k][0] or (w == best[k][0] and n > best[k][1])):
            prs += 1
        if k not in best or (w, n) > best[k]:
            best[k] = (w, n)
    streak, _, goal_weeks = week_streak(days, goal, today)
    return {"days": len({str(r["performed_on"]) for r in rows}), "prs": prs,
            "volume": sum(float(r["weight_kg"]) * int(r["reps"]) for r in rows),
            "streak": streak, "goal_weeks": goal_weeks + (1 if week_streak(days, goal, today)[1] >= goal else 0),
            "body": body_n}


def _achievements(sc, m, rows, days, goal):
    try:
        body_n = len(sc.table("body_logs").select("id").eq("member_id", m["id"]).limit(5).execute().data or [])
    except Exception:
        body_n = 0
    a = achievement_stats(_sets(sc, m, days=3000) if rows else [], days, goal, body_n)
    got = [x for x in ACHIEVEMENTS if x[3](a)]
    gw._md(f'<div class="tr-sub" style="margin-bottom:8px">{len(got)} of {len(ACHIEVEMENTS)} unlocked</div>'
           '<div class="tr-ach">' + "".join(
               f'<div class="{"" if x[3](a) else "off"}"><b>{x[1]}</b>{gw._esc(x[2])}</div>' for x in ACHIEVEMENTS)
           + '</div>')


# ------------------------------------------------------------------ member: challenges (visits)
def _challenges(sc, m, gym_days):
    today = gw.today_local()
    try:
        chs = sc.table("community_challenges").select("*").eq("gym_id", m["gym_id"]) \
            .gte("ends_on", today.isoformat()).lte("starts_on", (today + timedelta(days=30)).isoformat()) \
            .order("ends_on").limit(5).execute().data or []
    except Exception:
        return
    if not chs:
        return
    try:
        ents = sc.table("community_challenge_entries").select("*").in_("challenge_id", [c["id"] for c in chs]) \
            .execute().data or []
    except Exception:
        ents = []
    st.markdown('<div class="section-label">CHALLENGES</div>', unsafe_allow_html=True)
    for ch in chs:
        mine = next((e for e in ents if e["challenge_id"] == ch["id"] and e["member_id"] == m["id"]), None)
        s, e = (pd.Timestamp(str(ch["starts_on"])).date(), pd.Timestamp(str(ch["ends_on"])).date())
        n = len({d for d in gym_days if s <= d <= e})
        goal = int(ch["goal_visits"])
        joined = sum(1 for x in ents if x["challenge_id"] == ch["id"])
        with st.container(border=True, key=f"tr_ch_{ch['id']}"):
            st.markdown(f"**{ch.get('badge') or '🏆'} {ch['title']}**")
            st.caption(f"{goal} gym visits · {s:%d %b} – {e:%d %b} · {joined} joined")
            if mine:
                st.progress(min(n, goal) / goal, text="Completed! 🎉" if n >= goal else f"{n} of {goal} visits")
                if n >= goal and not mine.get("completed_at"):
                    try:
                        sc.table("community_challenge_entries").update(
                            {"completed_at": datetime.now(timezone.utc).isoformat()}) \
                            .eq("challenge_id", ch["id"]).eq("member_id", m["id"]).execute()
                    except Exception:
                        pass
            elif s > today:
                st.caption(f"Starts {s:%a %d %b}.")
            elif st.button("Join", key=f"tr_join_{ch['id']}", type="primary", use_container_width=True):
                try:
                    sc.table("community_challenge_entries").insert({"challenge_id": ch["id"], "gym_id": m["gym_id"],
                                                                    "member_id": m["id"]}).execute()
                    st.session_state["tr_home_flash"] = "You're in. Every gym visit counts!"
                except Exception:
                    st.session_state["tr_home_flash"] = "You're already in this challenge."
                st.rerun()


# ------------------------------------------------------------------ member: body
def _body(sc, m):
    try:
        rows = sc.table("body_logs").select("*").eq("member_id", m["id"]).order("logged_on").limit(500).execute().data
    except Exception:
        st.info("Body tracking is coming soon to this gym.")
        return
    rows = rows or []
    flash = st.session_state.pop("tr_body_flash", None)
    if flash:
        st.success(flash)
    last = rows[-1] if rows else {}
    with st.form("tr_body", clear_on_submit=False):
        st.markdown("**Log today**")
        c1, c2, c3 = st.columns(3)
        w = c1.number_input("Weight (kg)", 0.0, 400.0, float(last.get("weight_kg") or 0), 0.1, key="tr_bw")
        waist = c2.number_input("Waist (cm)", 0.0, 250.0, float(last.get("waist_cm") or 0), 0.5, key="tr_bwaist")
        fat = c3.number_input("Body fat %", 0.0, 70.0, float(last.get("body_fat") or 0), 0.1, key="tr_bfat")
        if st.form_submit_button("Save", type="primary", use_container_width=True):
            row = {"gym_id": m["gym_id"], "member_id": m["id"], "logged_on": gw.today_local().isoformat(),
                   "weight_kg": w if w >= 20 else None, "waist_cm": waist if waist >= 30 else None,
                   "body_fat": fat if fat >= 2 else None}
            if not any(row[k] for k in ("weight_kg", "waist_cm", "body_fat")):
                st.error("Enter at least one number.")
            else:
                try:
                    sc.table("body_logs").upsert(row, on_conflict="member_id,logged_on").execute()
                    st.session_state["tr_body_flash"] = "Saved. Weigh in at the same time of day for the fairest trend."
                except Exception:
                    st.session_state["tr_body_flash"] = "Couldn't save that. Please try again."
                st.rerun()
    if not rows:
        st.caption("Log your weight once a week to see your trend here. Only you can see it.")
        return
    df = pd.DataFrame(rows)
    df["day"] = pd.to_datetime(df["logged_on"])
    for col, label, unit in (("weight_kg", "Weight", "kg"), ("waist_cm", "Waist", "cm"), ("body_fat", "Body fat", "%")):
        d = df[pd.to_numeric(df[col], errors="coerce").notna()][["day", col]].copy()
        if d.empty:
            continue
        d[col] = d[col].astype(float)
        change = d[col].iloc[-1] - d[col].iloc[0]
        st.markdown(f"**{label}: {d[col].iloc[-1]:g} {unit}**"
                    + (f" · {'+' if change > 0 else ''}{change:.1f} {unit} since {d['day'].iloc[0]:%d %b}" if len(d) > 1 else ""))
        if len(d) > 1:
            try:
                import altair as alt
                st.altair_chart(alt.Chart(d).mark_line(color="#35D3E8", strokeWidth=3, point=True)
                                .encode(x=alt.X("day:T", title=None, axis=alt.Axis(format="%d %b", labelColor="#93A0B4")),
                                        y=alt.Y(f"{col}:Q", title=None, scale=alt.Scale(zero=False),
                                                axis=alt.Axis(labelColor="#93A0B4")))
                                .properties(height=170).configure(background="rgba(0,0,0,0)").configure_view(strokeWidth=0)
                                .configure_axis(gridColor="rgba(255,255,255,0.07)"), use_container_width=True)
            except Exception:
                st.line_chart(d.set_index("day")[col])


def _calendar(sc, m, rows):
    logged, gym = training_days(sc, m, rows, days=60)
    today = gw.today_local()
    start = today - timedelta(days=today.weekday() + 7 * 7)
    cells = []
    for i in range(8 * 7):
        d = start + timedelta(days=i)
        cls = "on" if d in logged else ("gym" if d in gym else "")
        if d == today:
            cls += " today"
        cells.append(f'<i class="{cls}" title="{d:%a %d %b}"></i>' if d <= today else '<i style="opacity:.2"></i>')
    st.markdown('<div class="section-label">LAST 8 WEEKS</div>', unsafe_allow_html=True)
    gw._md('<div class="tr-cal">' + "".join(cells) + '</div><div class="tr-sub" style="margin-top:6px">'
           'Green: workout logged · Blue: gym check-in</div>')



# ------------------------------------------------------------------ public machine guide page (QR on a machine)
def guide_link(gid):
    return f"{gw.APP_URL}/?guide={gid}"


def render_guide(supabase, gid):
    import gympulse_booking as gb
    gb._header()
    with gw.center("guide", 640):
        try:
            rows = supabase.rpc("gp_guide", {"p_id": str(gid)}).execute().data or []
        except Exception:
            rows = []
        if not rows:
            st.error("This guide isn't available. Please ask a coach.")
            return
        import gympulse_billing as gbill
        if gbill.gym_locked(gbill.gym_by("machine_guides", "id", gid)):
            gbill.render_gym_locked(rows[0].get("business_name"))
            return
        g = rows[0]
        gw._md(f'<div class="bk-sub">{gw._esc(g.get("business_name") or "")}</div>'
               f'<div class="bk-title">{gw._esc(g["name"])}</div>')
        if g.get("video_url"):
            st.video(g["video_url"])
        if g.get("tips"):
            st.markdown("**How to use it**")
            st.markdown(g["tips"])
        st.caption("Log your sets in the Train tab of your member app.")


# ------------------------------------------------------------------ owner: the Train page
def render_owner(supabase, gym_id):
    gw.page_header("Train", "What your members use at the gym: workouts, records, challenges and machine guides.",
                   "Member app")
    if not ready(supabase):
        st.info(SQL_HINT)
        return
    flash = st.session_state.pop("cmo_flash", None)
    if flash:
        st.success(flash)
    gym_name = gw._text((st.session_state.get("user_profile") or {}).get("business_name"), "Your gym")
    week = (gw.today_local() - timedelta(days=7)).isoformat()
    try:
        sets = supabase.table("workout_sets").select("member_id, weight_kg, reps").eq("gym_id", gym_id) \
            .gte("performed_on", week).limit(20000).execute().data or []
    except Exception:
        sets = []
    gw.kpi_row([("Members logging", str(len({s['member_id'] for s in sets})), "lime", "last 7 days"),
                ("Sets logged", f"{len(sets):,}", "cyan", "last 7 days"),
                ("Kg lifted", f"{sum(float(s['weight_kg']) * int(s['reps']) for s in sets):,.0f}", "amber", "last 7 days")])
    t1, t2, t3, t4, t5 = st.tabs(["Today's workout", "Machine guides", "Challenges", "Gym now", "Insights"])
    with t1:
        _owner_wod(supabase, gym_id)
    with t2:
        _owner_guides(supabase, gym_id, gym_name)
    with t3:
        _owner_challenges(supabase, gym_id)
    with t4:
        _owner_traffic(supabase, gym_id)
    with t5:
        _owner_insights(supabase, gym_id)


def _owner_traffic(supabase, gym_id):
    import gympulse_admin as gadm
    prof = st.session_state.get("user_profile") or {}
    cfg = traffic_cfg(prof)
    st.caption("What members see in Train → Gym now: people inside right now, the usual for every half hour and "
               "the quietest times. It's only as accurate as your check-ins, so make sure every member checks in.")
    sc = gadm.service_client() or supabase
    data = traffic(sc, gym_id, cfg["visit"])
    if data is None:
        st.info("Run sql/phase31_gym_traffic.sql in Supabase to switch on accurate gym busyness.")
    else:
        render_traffic(data, inside_now(sc, gym_id, cfg["visit"]), cfg, key="trow_tf")
    if st.session_state.get("role") == "staff":
        return
    with st.form("tr_traffic_cfg"):
        st.markdown("**Settings**")
        visit = st.slider("Average visit length (minutes)", 30, 180, cfg["visit"], 5,
                          help="How long a typical member trains. Each check-in counts as inside the gym this long.")
        use = st.toggle("Set opening hours", value=bool(cfg["hours"]),
                        help="Otherwise GymPulse works out your hours from when members check in.")
        st.caption("Pick the exact time, to the minute in 5s: tap the box and type, e.g. 5:30 or 10:45.")
        cur = cfg["hours"] or {}
        default = {"wk": [330, 1320], "sat": [420, 1200], "sun": [480, 1080]}
        picked = {}
        for g, label in GROUPS.items():
            span = cur.get(g, default[g]) if g in cur or not cur else None
            st.markdown(f"**{label}**")
            c1, c2, c3 = st.columns([1, 1, 1], vertical_alignment="bottom")
            shut = c3.checkbox("Closed", value=bool(cur) and span is None, key=f"tr_h_{g}_x")
            span = span or default[g]
            o = c1.selectbox("Opens", OPEN_TIMES, index=OPEN_TIMES.index(span[0] - span[0] % 5),
                             format_func=clock, key=f"tr_h_{g}_o")
            cl = c2.selectbox("Closes", CLOSE_TIMES, index=CLOSE_TIMES.index(max(5, span[1] - span[1] % 5)),
                              format_func=lambda x: "Midnight" if x == 1440 else clock(x), key=f"tr_h_{g}_c")
            picked[g] = None if shut else [int(o), int(cl)]
        if st.form_submit_button("Save", type="primary"):
            bad = [GROUPS[g] for g, v in picked.items() if v and v[1] <= v[0]]
            if use and bad:
                st.error("Closing time must be after opening time: " + ", ".join(bad) + ".")
            else:
                import gympulse_grow as gg
                val = {"visit": int(visit), "hours": picked if use else None}
                gg._save_settings(supabase, prof.get("id"), {"traffic": val}, "Gym now settings saved.")
                st.session_state["cmo_flash"] = "Gym now settings saved."
                st.rerun()


def _owner_challenges(sc, gym_id):
    st.caption("A visit challenge members join from the Train tab, e.g. 12 visits in a month. Every gym check-in "
               "counts, and members see their progress.")
    with st.form("tr_new_ch", clear_on_submit=True):
        a, b = st.columns([3, 1])
        title = a.text_input("Name", placeholder=f"e.g. 12 visits in {gw.today_local():%B}")
        badge = b.selectbox("Badge", ["🏆", "🔥", "💪", "⭐", "🥇", "🏃", "🧘"])
        c, d, e = st.columns(3)
        goal = c.number_input("Visits to finish", 1, 100, 12)
        start = d.date_input("Starts", value=gw.today_local())
        end = e.date_input("Ends", value=gw.today_local() + timedelta(days=30))
        if st.form_submit_button("Start challenge", type="primary"):
            if not title.strip() or end < start:
                st.error("Give it a name, and an end date after the start.")
            else:
                try:
                    sc.table("community_challenges").insert({"gym_id": gym_id, "title": title.strip()[:80],
                                                             "goal_visits": int(goal), "starts_on": start.isoformat(),
                                                             "ends_on": end.isoformat(), "badge": badge}).execute()
                    st.session_state["cmo_flash"] = "Challenge started: members see it in their Train tab."
                except Exception:
                    st.session_state["cmo_flash"] = ("Challenges need a one-time setup: run "
                                                     "sql/phase24_community_engage.sql in Supabase.")
                st.rerun()
    try:
        chs = sc.table("community_challenges").select("*").eq("gym_id", gym_id).order("ends_on", desc=True) \
            .limit(10).execute().data or []
        ents = sc.table("community_challenge_entries").select("*").in_("challenge_id", [c["id"] for c in chs]) \
            .execute().data or [] if chs else []
    except Exception:
        chs, ents = [], []
    gw.table([{"Challenge": f"{c.get('badge') or ''} {c['title']}", "Goal": f"{c['goal_visits']} visits",
               "Dates": f"{pd.Timestamp(str(c['starts_on'])):%d %b} – {pd.Timestamp(str(c['ends_on'])):%d %b}",
               "Joined": sum(1 for e in ents if e["challenge_id"] == c["id"]),
               "Finished": sum(1 for e in ents if e["challenge_id"] == c["id"] and e.get("completed_at"))}
              for c in chs], empty="No challenges yet.")


def _owner_insights(sc, gym_id):
    since = (gw.today_local() - timedelta(days=30)).isoformat()
    try:
        sets = gw.fetch_all(sc.table("workout_sets").select("member_id, exercise, weight_kg, reps, performed_on")
                            .eq("gym_id", gym_id).gte("performed_on", since).order("id"))
    except Exception:
        sets = []
    if not sets:
        st.info("When members log workouts in their Train tab, you'll see what they train and who's most "
                "consistent here.")
        return
    df = pd.DataFrame(sets)
    members, _ = gw.fetch_members(sc, gym_id, archived=False, include_photo=False)
    names = dict(zip(members["id"], members["full_name"])) if not members.empty else {}
    top = df.groupby("exercise").agg(Sets=("exercise", "size"), Members=("member_id", "nunique")) \
        .sort_values("Sets", ascending=False).head(10).reset_index().rename(columns={"exercise": "Exercise"})
    st.markdown("**Most-trained exercises · last 30 days**")
    gw.table(top.to_dict("records"))
    days = df.groupby("member_id")["performed_on"].nunique().sort_values(ascending=False).head(10)
    st.markdown("**Most consistent members · last 30 days**")
    st.caption("Only you see this. Great people to thank, or to ask for a review.")
    gw.table([{"Member": names.get(mid, "Member"), "Workouts logged": int(n)} for mid, n in days.items()])


def _owner_wod(supabase, gym_id):
    st.caption("One short workout a day keeps the Train tab fresh. Members see it at the top and tap an exercise to log it.")
    author = gw._text((st.session_state.get("staff") or {}).get("full_name")) or \
        gw._text((st.session_state.get("user_profile") or {}).get("full_name"))
    with st.form("tr_wod", clear_on_submit=True):
        day = st.date_input("Day", value=gw.today_local())
        title = st.text_input("Title", max_chars=80, placeholder="e.g. Leg day, Full body burner")
        body = st.text_area("Workout", max_chars=2000, height=160,
                            placeholder="Squat 5 × 5\nRomanian deadlift 3 × 10\nLunges 3 × 12 each leg\nPlank 3 × 45 s")
        if st.form_submit_button("Post workout", type="primary"):
            if not title.strip() or not body.strip():
                st.error("Add a title and the workout.")
            else:
                supabase.table("coach_workouts").upsert(
                    {"gym_id": gym_id, "day": day.isoformat(), "title": title.strip(), "body": body.strip(),
                     "author": author or None}, on_conflict="gym_id,day").execute()
                st.session_state["cmo_flash"] = f"Workout posted for {day:%a %d %b}."
                st.rerun()
    try:
        recent = supabase.table("coach_workouts").select("*").eq("gym_id", gym_id).order("day", desc=True) \
            .limit(5).execute().data or []
    except Exception:
        recent = []
    for w in recent:
        with st.container(border=True):
            st.markdown(f"**{pd.Timestamp(str(w['day'])):%a %d %b}** · {w['title']}")
            st.caption(w["body"][:200])


def _owner_guides(supabase, gym_id, gym_name):
    st.caption("Film a 30-second video on each machine, add it here and stick the QR code on the machine. Members "
               "scan it to see how to use it: no login needed.")
    with st.form("tr_guide", clear_on_submit=True):
        c1, c2 = st.columns(2)
        name = c1.text_input("Machine", max_chars=80, placeholder="e.g. Leg press")
        ex = c2.selectbox("Exercise it's for (optional)", [""] + EXERCISES)
        video = st.file_uploader("Video (MP4 or MOV, up to 45 MB)", type=["mp4", "mov", "m4v", "webm"])
        link = st.text_input("…or a video link (YouTube, Instagram)", placeholder="https://")
        tips = st.text_area("Tips", max_chars=800, placeholder="Feet shoulder-width apart\nDon't lock your knees")
        if st.form_submit_button("Add guide", type="primary"):
            url = link.strip() or None
            if video is not None:
                if video.size > 45 * 1024 * 1024:
                    st.error("That video is over 45 MB. Trim it or use a link.")
                    st.stop()
                url = _upload_video(supabase, gym_id, video)
                if not url:
                    st.error("The video couldn't be uploaded. Try again, or use a link.")
                    st.stop()
            if not name.strip():
                st.error("Name the machine.")
            else:
                supabase.table("machine_guides").insert({"gym_id": gym_id, "name": name.strip(), "exercise": ex or None,
                                                         "video_url": url, "tips": tips.strip() or None}).execute()
                st.session_state["cmo_flash"] = f"Guide added: {name.strip()}. Print its QR code below."
                st.rerun()
    try:
        guides = supabase.table("machine_guides").select("*").eq("gym_id", gym_id).order("name").execute().data or []
    except Exception:
        guides = []
    import gympulse_reports as rp
    import gympulse_signup as gsign
    for g in guides:
        with st.container(border=True, key=f"tr_g_{g['id']}"):
            a, b = st.columns([3, 1])
            with a:
                st.markdown(f"**{g['name']}**" + (f" · {g['exercise']}" if g.get("exercise") else ""))
                st.caption(("🎬 Video added" if g.get("video_url") else "No video yet") + (" · tips" if g.get("tips") else ""))
                st.code(guide_link(g["id"]), language=None)
                if st.button("Delete", key=f"tr_gdel_{g['id']}", type="tertiary"):
                    supabase.table("machine_guides").delete().eq("id", g["id"]).execute()
                    st.rerun()
            with b:
                png = gsign._qr_png(guide_link(g["id"]))
                st.image(png, use_container_width=True)
                rp.download_link("QR", png, f"qr-{g['name'].lower().replace(' ', '-')}.png", "image/png", f"tr_q_{g['id']}")


def _upload_video(supabase, gym_id, f):
    ext = (f.name.rsplit(".", 1)[-1] or "mp4").lower()
    path = f"{gym_id}/guide_{uuid.uuid4().hex}.{ext}"
    try:
        store = supabase.storage.from_(BUCKET)
        store.upload(path, f.getvalue(), {"content-type": f.type or "video/mp4"})
        url = store.get_public_url(path)
        if isinstance(url, dict):
            url = url.get("publicURL") or url.get("publicUrl") or ""
        return str(url).split("?")[0] or None
    except Exception:
        return None
