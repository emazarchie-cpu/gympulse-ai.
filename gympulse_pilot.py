"""Phase 5: pilot and commercial readiness.

* Getting-started checklist so a new gym reaches value quickly.
* Retention operations KPIs (coverage, speed, completion, conversion).
* Pilot scorecard: save a baseline when a pilot starts, then compare.
* Data export for pilot analysis and support.

Baselines are saved in the owner's profile settings; no new table needed.
"""
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw


def _ts(series):
    return pd.to_datetime(series, errors="coerce", utc=True, format="ISO8601").dt.tz_localize(None)


# ------------------------------------------------------------------ onboarding
def checklist(supabase, gym_id, roster, missing, actions):
    import gympulse_automation as ga
    ck = None
    try:
        ck = gw.load_checkins(supabase, gym_id)
    except Exception:
        pass
    week = 0
    if ck is not None and not ck.empty:
        week = int(((pd.Timestamp(gw.today_local()) - ck["day"]).dt.days < 7).sum())
    trainers = []
    try:
        trainers = gw.load_trainers(supabase, gym_id)
    except Exception:
        pass
    has_actions = actions is not None and not actions.empty
    members_n = len(roster) + (len(missing) if missing is not None else 0)
    steps = [
        ("Add your members", members_n > 0, "Member Management"),
        ("Give every member a plan and fee", members_n > 0 and (missing is None or missing.empty),
         "Risk Radar"),
        ("Check members in this week", week > 0, "Check-in"),
        ("Add your trainers", bool(trainers), "Settings"),
        ("Start your first retention play", has_actions, "Action Centre"),
        ("Record an outcome", has_actions and bool((actions["status"] == "Done").any()), "Action Centre"),
        ("Set up your team and automation", bool(ga.staff_list()) or ga.automation_settings()["enabled"],
         "Settings"),
    ]
    return steps


def render_checklist(supabase, gym_id, roster, missing, actions):
    s = dict((st.session_state.get("user_profile") or {}).get("settings") or {})
    if s.get("onboarding_hidden") or st.session_state.get("_onb_hidden"):
        return
    steps = checklist(supabase, gym_id, roster, missing, actions)
    done = sum(1 for _, ok, _ in steps if ok)
    if done == len(steps):
        return
    pct = round(done / len(steps) * 100)
    with st.expander(f"Getting started · {done} of {len(steps)} done", expanded=done < 3):
        gw._md(f'<div class="cc-step-bar" style="margin:0 0 12px"><span style="width:{pct}%"></span></div>')
        for i, (label, ok, page) in enumerate(steps):
            c1, c2 = st.columns([4, 1], vertical_alignment="center")
            mark = "✅" if ok else "⬜"
            c1.markdown(f"{mark} {'~~' + label + '~~' if ok else '**' + label + '**'}")
            if not ok:
                c2.button("Open", key=f"onb_{i}", on_click=gw._go, args=(page,),
                          use_container_width=True)
        if st.button("Hide this checklist", key="onb_hide", type="tertiary"):
            st.session_state["_onb_hidden"] = True
            st.rerun()


# ------------------------------------------------------------------ operations KPIs
def operations_kpis(roster, actions, days=30):
    """Level 2 KPIs: is the team acting on risk, quickly, and finishing the job?"""
    out = {"coverage": None, "at_risk": 0, "covered": 0, "hours_to_contact": None,
           "completion": None, "conversion": None, "assigned_share": None, "plays_n": 0}
    if roster.empty:
        return out
    risk = roster[roster["risk_category"] != "Low"]
    out["at_risk"] = len(risk)
    if actions is None or actions.empty:
        out["coverage"] = 0.0 if len(risk) else None
        return out
    a = actions.copy()
    now = pd.Timestamp.utcnow().tz_localize(None)
    since = now - pd.Timedelta(days=days)
    created = _ts(a["created_at"]) if "created_at" in a.columns else pd.Series(pd.NaT, index=a.index)
    recent = a[(created >= since) | (a["status"] != "Done")]
    covered = set(recent["member_id"]) & set(risk["id"])
    out["covered"] = len(covered)
    out["coverage"] = len(covered) / len(risk) if len(risk) else None
    win = a[created >= since]
    out["plays_n"] = len(win)
    if "contacted_at" in a.columns and len(win):
        gap = (_ts(win["contacted_at"]) - created[win.index]).dt.total_seconds() / 3600
        gap = gap[gap >= 0]
        out["hours_to_contact"] = float(gap.median()) if len(gap) else None
    if len(win):
        out["completion"] = float((win["status"] == "Done").mean())
        out_col = win["outcome"].fillna("") if "outcome" in win.columns else pd.Series("", index=win.index)
        kept, lost = int((out_col == "Retained").sum()), int((out_col == "Cancelled").sum())
        out["conversion"] = kept / (kept + lost) if kept + lost else None
        if "assigned_to" in win.columns:
            out["assigned_share"] = float(win["assigned_to"].notna().mean())
    return out


def _pct(x):
    return "n/a" if x is None else f"{x:.0%}"


def render_operations(roster, actions):
    k = operations_kpis(roster, actions)
    st.markdown('<div class="section-label">RETENTION OPERATIONS · LAST 30 DAYS</div>',
                unsafe_allow_html=True)
    speed = ("n/a" if k["hours_to_contact"] is None else
             f"{k['hours_to_contact']:.0f} h" if k["hours_to_contact"] < 48 else
             f"{k['hours_to_contact'] / 24:.1f} days")
    gw.kpi_row([
        ("Coverage", _pct(k["coverage"]), "cyan", f"{k['covered']} of {k['at_risk']} at-risk members have a play"),
        ("Time to first contact", speed, "amber", "Median, from play started to contacted"),
        ("Completion", _pct(k["completion"]), "lime", f"Of {k['plays_n']} plays started, share finished"),
        ("Conversion", _pct(k["conversion"]), "white", "Kept ÷ (kept + cancelled)"),
    ])
    st.caption("These show whether risk turns into action. Aim for high coverage, contact within a day, "
               "and every play closed with an outcome.")


# ------------------------------------------------------------------ pilot scorecard
def snapshot(supabase, gym_id, roster, actions):
    import gympulse_revenue as gr
    ops = operations_kpis(roster, actions)
    rate, _, _ = gr.renewal_rate(roster)
    return {
        "taken_on": gw.today_local().isoformat(),
        "members": int(len(roster)),
        "avg_visits": float(roster["visits_last_30_days"].mean()) if len(roster) else 0.0,
        "high_risk": int((roster["risk_category"] == "High").sum()) if len(roster) else 0,
        "at_risk_share": float((roster["risk_category"] != "Low").mean()) if len(roster) else 0.0,
        "renewal_rate": rate,
        "coverage": ops["coverage"],
        "conversion": ops["conversion"],
    }


METRICS = [
    ("members", "Members tracked", "{:.0f}", 1),
    ("avg_visits", "Average visits per member (30 days)", "{:.1f}", 1),
    ("high_risk", "High-risk members (estimate)", "{:.0f}", -1),
    ("at_risk_share", "Share at medium or high risk (estimate)", "pct", -1),
    ("renewal_rate", "Renewal rate (30 days)", "pct", 1),
    ("coverage", "At-risk members with a play", "pct", 1),
    ("conversion", "Play conversion", "pct", 1),
]


def _fmt(v, f):
    if v is None:
        return "n/a"
    return f"{v:.0%}" if f == "pct" else f.format(v)


def render_pilot(supabase, gym_id, roster, actions, save_settings):
    s = dict((st.session_state.get("user_profile") or {}).get("settings") or {})
    pilot = s.get("pilot") or {}
    st.markdown('<div class="section-label">PILOT SCORECARD</div>', unsafe_allow_html=True)
    now = snapshot(supabase, gym_id, roster, actions)
    if not pilot.get("baseline"):
        st.write("Starting a pilot? Save today's numbers as your baseline. GymPulse then shows how "
                 "attendance, renewals and follow-up habits change against it.")
        if st.button("Save today as my pilot baseline", key="pilot_start", type="primary"):
            save_settings({**s, "pilot": {"baseline": now}}, "Baseline saved. Your pilot has started.")
        return
    base = pilot["baseline"]
    started = date.fromisoformat(base["taken_on"])
    days = (gw.today_local() - started).days
    st.caption(f"Baseline saved on {started:%d %b %Y} · {days} day(s) into the pilot. "
               "Changes compare today with the baseline. They show direction, not proof of cause: "
               "seasons, prices and new members also move these numbers.")
    rows = []
    for key, label, f, good in METRICS:
        b, n = base.get(key), now.get(key)
        if b is None or n is None:
            change = "n/a"
        else:
            d = n - b
            sign = "+" if d > 0 else ""
            change = (f"{sign}{d * 100:.0f} pts" if f == "pct" else f"{sign}{_fmt(d, f)}")
            if d and (d > 0) == (good > 0):
                change += " ↑ better"
            elif d:
                change += " ↓ worse"
        rows.append({"Measure": label, "Baseline": _fmt(b, f), "Today": _fmt(n, f), "Change": change})
    gw.table(rows)
    if st.button("Reset the baseline to today", key="pilot_reset", type="tertiary"):
        save_settings({**s, "pilot": {"baseline": now}}, "Baseline reset to today.")


def save_profile_settings(supabase, settings, message):
    """Persist profile settings from any page (owner's own profile row)."""
    owner = (st.session_state.get("auth_user") or {}).get("id")
    profile = st.session_state.get("user_profile") or {}
    try:
        supabase.table("profiles").update({"settings": settings}).eq("id", owner).execute()
    except Exception as error:
        st.error(f"Could not save: {error}. Run sql/phase4_automation.sql to add profile settings.")
        return
    profile["settings"] = settings
    st.session_state["user_profile"] = profile
    st.session_state["ins_flash"] = message
    st.rerun()


# ------------------------------------------------------------------ export
def _local_dt(series):
    t = pd.to_datetime(series, errors="coerce", utc=True, format="ISO8601")
    return t.dt.tz_convert(gw.APP_TZ).dt.tz_localize(None)


def export_tables(supabase, gym_id, roster, actions):
    """Clean, owner-friendly tables for export: (sheet, DataFrame, formats)."""
    import gympulse_revenue as gr
    names = roster.set_index("id")["full_name"].to_dict() if not roster.empty else {}
    out = []
    if not roster.empty:
        m = pd.DataFrame({
            "Member": roster["full_name"],
            "Phone": roster.get("phone"), "Email": roster.get("email"),
            "Plan": roster.get("membership_type"),
            "Monthly fee": pd.to_numeric(roster.get("monthly_fee"), errors="coerce"),
            "Membership ends": pd.to_datetime(roster.get("membership_end"), errors="coerce"),
            "Days since last visit": roster.get("days_since_last_visit"),
            "Visits, last 30 days": roster.get("visits_last_30_days"),
            "Visits, previous 30 days": roster.get("visits_previous_30_days"),
            "Risk level (estimate)": roster.get("risk_category"),
            "Cancellation estimate": pd.to_numeric(roster.get("cancellation_probability"), errors="coerce"),
            "Why": [gw.risk_story(r)["why"] for _, r in roster.iterrows()],
            "Suggested play": roster.get("suggested_action"),
        })
        out.append(("Members and risk", m, {"Monthly fee": "money", "Membership ends": "date",
                                            "Cancellation estimate": "pct"}))
    if actions is not None and not actions.empty:
        a = actions
        col = lambda c: a[c] if c in a.columns else None
        import gympulse_automation as ga
        p = pd.DataFrame({
            "Member": a["member_id"].map(names).fillna("Former member"),
            "Play": col("action_type"),
            "Stage": [gw.action_stage(r) for r in a.to_dict("records")],
            "Outcome": col("outcome"),
            "Started": _local_dt(col("created_at")) if "created_at" in a.columns else None,
            "Contacted": _local_dt(col("contacted_at")) if "contacted_at" in a.columns else None,
            "Contact method": col("contact_method"),
            "Follow-up due": pd.to_datetime(col("due_date"), errors="coerce") if "due_date" in a.columns else None,
            "Closed": _local_dt(col("completed_at")) if "completed_at" in a.columns else None,
            "Assigned to": [ga.assigned_to(r) for r in a.to_dict("records")],
            "Note": col("note"),
        })
        out.append(("Retention plays", p, {"Started": "date", "Contacted": "date",
                                           "Follow-up due": "date", "Closed": "date"}))
    pay = gr.load_payments(supabase, gym_id)
    if pay is not None and not pay.empty:
        q = pd.DataFrame({
            "Date": pd.to_datetime(pay["paid_on"], errors="coerce"),
            "Member": pay["member_id"].map(names).fillna("Former member"),
            "Amount": pay["amount"],
            "Type": pay["kind"].map(gr.PAYMENT_KINDS).fillna("Payment"),
            "Plan": pay.get("plan"), "Paid by": pay.get("method"),
            "Covers until": pd.to_datetime(pay.get("covers_until"), errors="coerce"),
            "Credited to a play": ["No" if gw._blank(v) else "Yes" for v in pay["action_id"]],
            "Note": pay.get("note"),
        })
        out.append(("Payments", q, {"Date": "date", "Amount": "money", "Covers until": "date"}))
    return out


def render_export(supabase, gym_id, roster, actions):
    import gympulse_reports as rp
    st.markdown('<div class="section-label">EXPORT YOUR DATA</div>', unsafe_allow_html=True)
    try:
        tables = export_tables(supabase, gym_id, roster, actions)
    except Exception as error:
        st.error(f"Could not prepare the export: {error}")
        return
    if not tables:
        st.caption("Nothing to export yet.")
        return
    stamp = f"{gw.today_local():%Y-%m-%d}"
    cols = st.columns(len(tables) + 1)
    for col, (name, df, fmt) in zip(cols, tables):
        with col:
            rp.download_link(f"{name} (Excel)", rp.build_xlsx([(name, df, fmt)], name),
                             f"GymPulse-{name.replace(' ', '-').lower()}-{stamp}.xlsx", rp.XLSX,
                             f"exp_{name[:4]}")
    with cols[-1]:
        rp.download_link("Everything (Excel)", rp.build_xlsx(tables, "Full export"),
                         f"GymPulse-full-export-{stamp}.xlsx", rp.XLSX, "exp_all", primary=True)
    st.caption("Exports contain your members' personal details. Store them securely.")
