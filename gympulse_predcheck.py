"""GymPulse AI · Prediction check: are the cancellation predictions actually right?

How it works
* On the first visit of each month (or when the owner taps "Start a check today") every member's
  risk score is frozen in prediction_snapshots (sql/phase32_prediction_check.sql).
* 30 days later the page compares those frozen scores with what actually happened:
  who was archived, deleted, suspended, let their membership run out, or simply stopped coming.
* The owner can correct any member ("actually stayed" / "actually left"); a correction beats the
  automatic answer.
* It reports, in plain words: how many of the people who left were flagged in advance (catch rate),
  how many flagged people stayed anyway (false alarms), and whether High risk members really left
  more often than Low risk ones.
"""
from datetime import timedelta

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

WINDOW_DAYS = 30          # how long a check runs
AWAY_DAYS = 30            # no visit for this long by the end = stopped coming
GRACE_DAYS = 7            # membership ended this long ago and not renewed = left
FLAGGED = ("High", "Medium")
RISK_PILL = {"High": "red", "Medium": "amber", "Low": "lime"}
TABLE = "prediction_snapshots"


# ------------------------------------------------------------------ saving scores
def _ready(supabase, gym_id):
    try:
        supabase.table(TABLE).select("id").eq("gym_id", gym_id).limit(1).execute()
        return True
    except Exception:
        return False


def _dates(supabase, gym_id):
    try:
        rows = gw.fetch_all(supabase.table(TABLE).select("taken_on").eq("gym_id", gym_id)
                            .order("taken_on", desc=True).order("id"))
    except Exception:
        return []
    out = []
    for r in rows:
        d = pd.to_datetime(r.get("taken_on"), errors="coerce")
        if not pd.isna(d) and d.date() not in out:
            out.append(d.date())
    return sorted(out, reverse=True)


def take_snapshot(supabase, gym_id, assess_fn, day=None):
    """Freeze today's score for every scored member. Returns how many were saved."""
    day = day or gw.today_local()
    roster, _ = gw.load_roster(supabase, gym_id, assess_fn, with_photos=False)
    if roster is None or roster.empty:
        return 0
    rows = []
    for _, m in roster.iterrows():
        end = pd.to_datetime(m.get("membership_end"), errors="coerce")
        away = pd.to_numeric(m.get("days_since_last_visit"), errors="coerce")
        rows.append({
            "gym_id": gym_id, "member_id": str(m["id"]), "taken_on": day.isoformat(),
            "full_name": gw._text(m.get("full_name")),
            "probability": round(float(m["cancellation_probability"]), 4),
            "risk": m["risk_category"], "drivers": gw._text(m.get("drivers"))[:500],
            "days_away": None if pd.isna(away) else int(away),
            "membership_end": None if pd.isna(end) else end.date().isoformat(),
        })
    for start in range(0, len(rows), 500):
        (supabase.table(TABLE).upsert(rows[start:start + 500], on_conflict="gym_id,member_id,taken_on")
         .execute())
    return len(rows)


def ensure_monthly(supabase, gym_id, assess_fn):
    """Start this month's check automatically the first time the app is opened in the month.
    Quiet: never shows an error (the table may not exist yet)."""
    if not gym_id:
        return
    today = gw.today_local()
    key = f"_predcheck_{gym_id}_{today:%Y-%m}"
    if st.session_state.get(key):
        return
    st.session_state[key] = True
    try:
        rows = (supabase.table(TABLE).select("id").eq("gym_id", gym_id)
                .gte("taken_on", today.replace(day=1).isoformat()).limit(1).execute().data)
        if not rows:
            take_snapshot(supabase, gym_id, assess_fn, today)
    except Exception:
        pass


# ------------------------------------------------------------------ what actually happened
def _outcomes(supabase, gym_id, assess_fn, snap, as_of):
    """Work out, for each saved member, whether they left and why."""
    members, _ = gw.fetch_members(supabase, gym_id, archived=None, include_photo=False)
    info = {str(r["id"]): r for r in members.to_dict("records")} if not members.empty else {}
    try:
        roster, _ = gw.load_roster(supabase, gym_id, assess_fn, with_photos=False)
    except Exception:
        roster = pd.DataFrame()
    away = ({str(i): d for i, d in zip(roster["id"], roster["days_since_last_visit"])}
            if roster is not None and not roster.empty else {})
    left, why = [], []
    for _, s in snap.iterrows():
        mid = str(s["member_id"])
        m = info.get(mid)
        reason = ""
        if m is None:
            reason = "Removed from your members"
        elif bool(m.get("archived")):
            reason = "Archived"
        elif bool(m.get("suspended")):
            reason = "Paused / suspended"
        else:
            end = pd.to_datetime(m.get("membership_end"), errors="coerce")
            if not pd.isna(end) and end.date() < as_of - timedelta(days=GRACE_DAYS) \
                    and end.date() >= s["taken_on"] - timedelta(days=GRACE_DAYS):
                reason = f"Membership ended {end:%d %b}, not renewed"
            else:
                d = pd.to_numeric(away.get(mid), errors="coerce")
                if not pd.isna(d) and d >= AWAY_DAYS:
                    reason = f"Stopped coming ({int(d)} days without a visit)"
        auto = bool(reason)
        fix = s.get("outcome")
        if fix in ("left", "stayed"):
            left.append(fix == "left")
            why.append(("You marked: left" if fix == "left" else "You marked: stayed")
                       + (f" · auto said: {reason}" if reason and fix == "stayed" else ""))
        else:
            left.append(auto)
            why.append(reason or "Still a member and still coming")
    out = snap.copy()
    out["left"] = left
    out["why"] = why
    return out


def summarise(df):
    """The numbers behind the verdict. df needs columns risk, probability, left."""
    n = len(df)
    gone = int(df["left"].sum())
    flagged = df["risk"].isin(FLAGGED)
    caught = int((flagged & df["left"]).sum())
    alarms = int((flagged & ~df["left"]).sum())
    levels = []
    for lv in ("High", "Medium", "Low"):
        g = df[df["risk"] == lv]
        levels.append({"level": lv, "members": len(g), "left": int(g["left"].sum()),
                       "rate": (g["left"].mean() if len(g) else None)})
    return {"n": n, "left": gone, "caught": caught, "flagged": int(flagged.sum()), "alarms": alarms,
            "catch_rate": (caught / gone) if gone else None,
            "alarm_rate": (alarms / int(flagged.sum())) if flagged.any() else None,
            "predicted": float(df["probability"].mean()) if n else 0.0,
            "actual": (gone / n) if n else 0.0, "levels": levels}


def verdict(s, finished):
    """One plain-English paragraph on how the predictions did."""
    if s["n"] == 0:
        return "No members were saved in this check."
    lead = "" if finished else "So far: "
    if s["left"] == 0:
        return (lead + f"none of the {s['n']} members has left yet, so there's nothing to compare. "
                "That's good news for the gym, but it doesn't test the predictions.")
    parts = [lead + f"{s['left']} of {s['n']} members left. GymPulse flagged "
             f"{s['caught']} of them in advance ({s['catch_rate']:.0%})."]
    if s["flagged"]:
        parts.append(f"Of the {s['flagged']} members it flagged as High or Medium risk, "
                     f"{s['alarms']} stayed anyway.")
    rates = {x["level"]: x["rate"] for x in s["levels"] if x["members"]}
    if "High" in rates and "Low" in rates:
        if rates["High"] > rates["Low"]:
            parts.append(f"High risk members left far more often than Low risk ones "
                         f"({rates['High']:.0%} vs {rates['Low']:.0%}), which is what a useful score should do."
                         if rates["High"] >= rates["Low"] + 0.2 else
                         f"High risk members left a bit more often than Low risk ones "
                         f"({rates['High']:.0%} vs {rates['Low']:.0%}).")
        else:
            parts.append(f"High risk members did NOT leave more often than Low risk ones "
                         f"({rates['High']:.0%} vs {rates['Low']:.0%}), so the scores need work for your gym.")
    if s["left"] < 5 or s["n"] < 20:
        parts.append("This is a small group, so treat it as an early sign, not proof. "
                     "Run two or three months before judging.")
    return " ".join(parts)


# ------------------------------------------------------------------ page
def _pct(x):
    return "–" if x is None else f"{x:.0%}"


def _save_fixes(supabase, gym_id, day, edited, before):
    changed = 0
    for mid, choice in edited.items():
        if choice == before.get(mid):
            continue
        value = {"Left": "left", "Stayed": "stayed"}.get(choice)
        (supabase.table(TABLE).update({"outcome": value}).eq("gym_id", gym_id)
         .eq("member_id", mid).eq("taken_on", day.isoformat()).execute())
        changed += 1
    return changed


def render(supabase, gym_id, assess_fn):
    gw.page_header("Prediction check",
                   "Are the cancellation predictions right for your gym? GymPulse saves every member's "
                   "risk score at the start, then checks 30 days later who actually left.",
                   "Model accuracy")
    flash = st.session_state.pop("pc_flash", None)
    if flash:
        st.success(flash)
    if not gym_id:
        st.warning("No gym workspace found for your account.")
        return
    if not _ready(supabase, gym_id):
        st.info("One quick setup step: run **sql/phase32_prediction_check.sql** in Supabase "
                "(SQL Editor → New query → paste → Run), then reload this page.")
        return

    days = _dates(supabase, gym_id)
    today = gw.today_local()

    def start_button(label, key, primary=False):
        if st.button(label, key=key, type="primary" if primary else "secondary"):
            try:
                n = take_snapshot(supabase, gym_id, assess_fn, today)
            except Exception as error:
                st.error(f"Couldn't save the scores: {error}")
                return
            st.session_state["pc_flash"] = (f"Saved today's risk scores for {n} members. "
                                            f"Come back on {today + timedelta(days=WINDOW_DAYS):%d %b} "
                                            "for the result." if n else
                                            "No members have scores yet. Add attendance data first.")
            st.rerun()

    if not days:
        st.markdown(
            "**How it works**\n\n"
            "1. Today, GymPulse saves every member's risk score. They're locked, so nothing can be "
            "changed afterwards.\n"
            f"2. Over the next {WINDOW_DAYS} days, keep using GymPulse as normal: check-ins, renewals, "
            "archiving members who leave.\n"
            "3. At the end, this page shows who actually left and whether GymPulse saw it coming.\n\n"
            "A new check also starts by itself on the first visit of every month.")
        start_button("Start a check today", "pc_start_first", primary=True)
        return

    labels = {}
    for d in days:
        end = d + timedelta(days=WINDOW_DAYS)
        labels[d] = (f"Started {d:%d %b %Y} · finished {end:%d %b}" if today >= end else
                     f"Started {d:%d %b %Y} · day {(today - d).days} of {WINDOW_DAYS}")
    c1, c2 = st.columns([3, 1])
    day = c1.selectbox("Check", days, format_func=labels.get, key="pc_day")
    with c2:
        st.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)
        if today not in days:
            start_button("Start a new check today", "pc_start")

    try:
        snap = pd.DataFrame(gw.fetch_all(supabase.table(TABLE).select("*").eq("gym_id", gym_id)
                                         .eq("taken_on", day.isoformat()).order("id")))
    except Exception as error:
        st.error(f"Couldn't load this check: {error}")
        return
    if snap.empty:
        st.info("No members were saved in this check.")
        return
    snap["taken_on"] = day
    snap["probability"] = pd.to_numeric(snap["probability"], errors="coerce").fillna(0)
    end = day + timedelta(days=WINDOW_DAYS)
    finished = today >= end
    df = _outcomes(supabase, gym_id, assess_fn, snap, min(today, end))
    s = summarise(df)

    if not finished:
        st.info(f"This check is still running: {(end - today).days} days to go (ends {end:%d %b}). "
                "The numbers below are what's happened so far.")

    gw.kpi_row([
        ("Members checked", s["n"], "cyan", f"Scores saved {day:%d %b}"),
        ("Left", s["left"], "red", "Cancelled, paused or stopped coming"),
        ("Caught early", f"{s['caught']} of {s['left']}" if s["left"] else "–", "lime",
         f"Catch rate {_pct(s['catch_rate'])}"),
        ("False alarms", f"{s['alarms']} of {s['flagged']}" if s["flagged"] else "–", "amber",
         "Flagged but stayed"),
        ("Predicted vs actual", f"{s['predicted']:.0%} / {s['actual']:.0%}", "white",
         "Average score vs share who left"),
    ])
    gw._md(f'<div class="panel"><b>The verdict.</b> {gw._esc(verdict(s, finished))}</div>')

    st.markdown('<div class="section-label">BY RISK LEVEL · HIGH SHOULD LEAVE MOST, LOW LEAST</div>',
                unsafe_allow_html=True)
    gw.table([{"Risk": x["level"], "Members": x["members"], "Left": x["left"],
               "% left": _pct(x["rate"])} for x in s["levels"]], pills={"Risk": RISK_PILL})

    st.markdown('<div class="section-label">EVERY MEMBER · SCORE AT THE START VS WHAT HAPPENED</div>',
                unsafe_allow_html=True)
    view = df.sort_values("probability", ascending=False)
    rows = []
    for _, r in view.iterrows():
        flagged = r["risk"] in FLAGGED
        result = ("Caught" if flagged and r["left"] else "Missed" if r["left"] else
                  "False alarm" if flagged else "Correct")
        rows.append({"Member": r.get("full_name") or "Member", "Score then": f"{r['probability']:.0%}",
                     "Risk then": r["risk"], "What happened": "Left" if r["left"] else "Stayed",
                     "Prediction": result, "Why": r["why"]})
    gw.table(rows, pills={"Risk then": RISK_PILL, "What happened": {"Left": "red", "Stayed": "lime"},
                          "Prediction": {"Caught": "lime", "Correct": "lime", "Missed": "red",
                                         "False alarm": "amber"}}, wide=("Why",))
    st.download_button("Download this check (CSV)", pd.DataFrame(rows).to_csv(index=False).encode(),
                       file_name=f"gympulse-prediction-check-{day.isoformat()}.csv", mime="text/csv",
                       on_click="ignore", key=f"pc_csv_{day.isoformat()}")

    with st.expander("Correct a result (if GymPulse got someone's outcome wrong)"):
        st.caption("Leave “Automatic” unless you know better, e.g. a client told you they're quitting, "
                   "or someone who looks gone is just travelling.")
        names = view.drop_duplicates("member_id")
        before = {str(r["member_id"]): {"left": "Left", "stayed": "Stayed"}.get(r.get("outcome"), "Automatic")
                  for _, r in names.iterrows()}
        with st.form(f"pc_fix_{day.isoformat()}"):
            edited = {}
            for _, r in names.iterrows():
                mid = str(r["member_id"])
                opts = ["Automatic", "Left", "Stayed"]
                edited[mid] = st.selectbox(r.get("full_name") or "Member", opts,
                                           index=opts.index(before[mid]), key=f"pc_fix_{day}_{mid}")
            if st.form_submit_button("Save corrections"):
                try:
                    n = _save_fixes(supabase, gym_id, day, edited, before)
                except Exception as error:
                    st.error(f"Couldn't save: {error}")
                else:
                    st.session_state["pc_flash"] = f"Saved {n} correction(s)." if n else "Nothing changed."
                    st.rerun()

    st.caption(f"How “left” is decided: the member was archived, deleted or suspended; their membership "
               f"ended more than {GRACE_DAYS} days ago without a renewal; or they haven't visited for "
               f"{AWAY_DAYS}+ days. “Flagged” means High or Medium risk on the day the scores were saved.")
