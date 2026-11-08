"""GymPulse AI · Train: what members use while they're at the gym.

Member app → Train
  * Today's workout from the coach (one post a day by the gym).
  * Log: pick an exercise, see "last time: 60 kg × 8", log sets in two taps. Beating your best is a PR 🎉,
    which can be shared to the gym feed.
  * Progress: personal records and a chart per exercise.
  * Gym now: how busy it is right now and the usual pattern for today, from check-ins.
  * Tools: rest timer and plate calculator.
Owner (Community → Train): post today's workout; machine guides (video + tips) each with a QR code for the
machine. Scanning it opens a public guide page (?guide=<id>).
Database: sql/phase29_train.sql.
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
    _coach_card(sc, m)
    view = st.segmented_control("Train", ["Log", "Progress", "Gym now", "Tools"], default="Log", key="tr_view",
                                label_visibility="collapsed") or "Log"
    if view == "Log":
        _log(sc, m, gym_name)
    elif view == "Progress":
        _progress(sc, m)
    elif view == "Gym now":
        _busy(sc, m)
    else:
        _tools()


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
    pr = st.session_state.get("tr_pr")
    if pr:
        _share_pr(sc, m, gym_name, pr)
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
            st.session_state["tr_pr"] = {"ex": ex, "w": float(w), "r": int(r)}
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


def _share_pr(sc, m, gym_name, pr):
    import gympulse_community as gcom
    try:
        on = gcom.enabled(sc, m["gym_id"]) and m.get("community_agreed_at")
    except Exception:
        on = False
    if not on:
        st.session_state.pop("tr_pr", None)
        return
    a, b = st.columns(2)
    if a.button("Share my PR with the gym", icon=":material/emoji_events:", key="tr_share", use_container_width=True):
        try:
            sc.table("community_posts").insert({
                "gym_id": m["gym_id"], "member_id": m["id"], "author_name": gw._text(m.get("full_name"), "Member"),
                "body": f"🏆 New PR: {pr['ex']} {_fmt(pr['w'])} kg × {pr['r']}"}).execute()
            st.session_state["tr_flash"] = ("ok", "Shared with the gym 💪")
        except Exception:
            st.session_state["tr_flash"] = ("info", "Couldn't share right now.")
        st.session_state.pop("tr_pr", None)
        st.rerun()
    if b.button("Keep it private", key="tr_keep", use_container_width=True):
        st.session_state.pop("tr_pr", None)
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


def busy_data(sc, gym_id):
    """[(hour, usual)] for today's weekday and check-ins in the last 90 minutes."""
    try:
        rows = sc.rpc("gp_gym_busy", {"p_gym": gym_id}).execute().data or []
        if rows:
            return [(int(r["hour"]), float(r["usual"])) for r in rows], int(rows[0]["now_visits"])
    except Exception:
        pass
    return None, None


def _busy(sc, m):
    hours, now_n = busy_data(sc, m["gym_id"])
    if hours is None:
        st.info("Gym busyness will show here soon.")
        return
    hour = datetime.now(gw.APP_TZ).hour
    usual_now = next((u for h, u in hours if h == hour), 0)
    peak = max((u for _, u in hours), default=0)
    if now_n <= max(1, usual_now * 0.6):
        level, tone, note = "Quiet", "#B7F34A", "Great time to train: machines should be free."
    elif now_n <= usual_now * 1.3 + 1:
        level, tone, note = "Normal", "#FFC44D", "About as busy as usual for this time."
    else:
        level, tone, note = "Busy", "#FF6B6B", "Busier than usual right now."
    gw._md(f'<div class="mp-card"><div style="font-size:13px;color:#93A0B4">Right now</div>'
           f'<div style="font-size:30px;font-weight:900;color:{tone}">{level}</div>'
           f'<div>{now_n} check-in{"s" if now_n != 1 else ""} in the last 90 minutes. {note}</div></div>')
    open_hours = [(h, u) for h, u in hours if h >= hour]
    if open_hours and peak > 0:
        quiet = min(open_hours, key=lambda x: x[1])
        st.caption(f"Usually quietest later today around {quiet[0] % 12 or 12}{'am' if quiet[0] < 12 else 'pm'}.")
    df = pd.DataFrame(hours, columns=["hour", "usual"])
    df["label"] = [f"{h % 12 or 12}{'a' if h < 12 else 'p'}" for h in df["hour"]]
    df["now"] = ["Now" if h == hour else "Usual" for h in df["hour"]]
    try:
        import altair as alt
        chart = alt.Chart(df).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
            x=alt.X("label:N", sort=list(df["label"]), title=None, axis=alt.Axis(labelColor="#93A0B4", labelAngle=0)),
            y=alt.Y("usual:Q", title=None, axis=None),
            color=alt.Color("now:N", scale=alt.Scale(domain=["Now", "Usual"], range=["#B7F34A", "#35506B"]), legend=None),
            tooltip=[alt.Tooltip("label:N", title="Hour"), alt.Tooltip("usual:Q", title="Usual check-ins", format=".1f")])
        st.markdown(f"**Usually on {datetime.now(gw.APP_TZ):%A}s**")
        st.altair_chart(chart.properties(height=180).configure(background="rgba(0,0,0,0)").configure_view(strokeWidth=0),
                        use_container_width=True)
    except Exception:
        st.bar_chart(df.set_index("label")["usual"])


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
        g = rows[0]
        gw._md(f'<div class="bk-sub">{gw._esc(g.get("business_name") or "")}</div>'
               f'<div class="bk-title">{gw._esc(g["name"])}</div>')
        if g.get("video_url"):
            st.video(g["video_url"])
        if g.get("tips"):
            st.markdown("**How to use it**")
            st.markdown(g["tips"])
        st.caption("Log your sets in the Train tab of your member app.")


# ------------------------------------------------------------------ owner: Community → Train
def render_owner(supabase, gym_id):
    if not ready(supabase):
        st.info(SQL_HINT)
        return
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
    t1, t2 = st.tabs(["Today's workout", "Machine guides"])
    with t1:
        _owner_wod(supabase, gym_id)
    with t2:
        _owner_guides(supabase, gym_id, gym_name)


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
    import gympulse_community as gcom
    ext = (f.name.rsplit(".", 1)[-1] or "mp4").lower()
    path = f"{gym_id}/guide_{uuid.uuid4().hex}.{ext}"
    try:
        store = supabase.storage.from_(gcom.BUCKET)
        store.upload(path, f.getvalue(), {"content-type": f.type or "video/mp4"})
        url = store.get_public_url(path)
        if isinstance(url, dict):
            url = url.get("publicURL") or url.get("publicUrl") or ""
        return str(url).split("?")[0] or None
    except Exception:
        return None
