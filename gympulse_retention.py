"""GymPulse AI · Retention rate.

The share of members a gym keeps over a period, worked out from membership
dates (renewals move the end date forward, so a member who renewed counts as
kept):

  at the start   members who had joined before the period and whose membership
                 was still running when it began
  kept           those whose membership was still running at the end of the
                 period (or today, for the period in progress)
  lost           the rest: their membership ended during the period and
                 hasn't been renewed

Industry guide: gyms keep about 66% of members over a year (Health & Fitness
Association benchmarking), which is roughly 96–97% a month.
"""
from datetime import timedelta

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

INDUSTRY_YEAR = 66            # % of members kept over 12 months
INDUSTRY_MONTH = 96.6         # the same, per month (0.966 ** 12 ≈ 0.66)
MIN_BASE = 5                  # fewer members than this at the start: not enough to say


def members_all(supabase, gym_id):
    """Every member, including archived ones, with joined and end dates."""
    df, _ = gw.fetch_members(supabase, gym_id, archived=None, include_photo=False)
    if df.empty:
        return df
    df = df.copy()
    df["joined"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True, format="ISO8601") \
        .dt.tz_convert(gw.APP_TZ).dt.date
    df["end"] = pd.to_datetime(df["membership_end"], errors="coerce").dt.date
    return df


def rate(df, start, end):
    """{"base", "kept", "lost", "rate"} for the period start..end (dates, inclusive)."""
    if df is None or df.empty:
        return {"base": 0, "kept": 0, "lost": 0, "rate": None}
    base = kept = 0
    for _, m in df.iterrows():
        j, e = m["joined"], m["end"]
        if j is None or pd.isna(j) or j >= start:
            continue
        has_end = e is not None and not pd.isna(e)
        if not has_end:
            if m.get("archived"):
                continue                   # archived with no dates: we can't tell when they left
            base += 1
            kept += 1
            continue
        if e < start:
            continue                       # already gone before the period
        base += 1
        if e >= end:
            kept += 1
    return {"base": base, "kept": kept, "lost": base - kept,
            "rate": round(kept / base * 100, 1) if base >= MIN_BASE else None}


def month_ranges(today, n=6):
    """The last n months as (start, end), oldest first; the current month ends today."""
    out, first = [], today.replace(day=1)
    for _ in range(n):
        last = min(today, (first + timedelta(days=32)).replace(day=1) - timedelta(days=1))
        out.append((first, last))
        first = (first - timedelta(days=1)).replace(day=1)
    return out[::-1]


def summary(supabase, gym_id, today=None):
    today = today or gw.today_local()
    df = members_all(supabase, gym_id)
    first_this = today.replace(day=1)
    last_start = (first_this - timedelta(days=1)).replace(day=1)
    return {"df": df,
            "last_month": rate(df, last_start, first_this - timedelta(days=1)),
            "last_month_label": f"{last_start:%B}",
            "year": rate(df, today - timedelta(days=365), today),
            "trend": [(s, rate(df, s, e)) for s, e in month_ranges(today, 6)]}


def _fmt(r):
    return f"{r['rate']:.0f}%" if r["rate"] is not None else "–"


def render_insights(supabase, gym_id):
    """Business Insights: the gym's own retention rate against the industry."""
    s = summary(supabase, gym_id)
    lm, yr = s["last_month"], s["year"]
    st.markdown('<div class="section-label">RETENTION RATE</div>', unsafe_allow_html=True)
    gw.kpi_row([
        (f"Kept in {s['last_month_label']}", _fmt(lm), "lime",
         f"{lm['kept']} of {lm['base']} members" if lm["rate"] is not None else "not enough members yet"),
        (f"Lost in {s['last_month_label']}", str(lm["lost"]) if lm["rate"] is not None else "–", "red",
         "memberships ended, not renewed"),
        ("Kept over 12 months", _fmt(yr), "cyan",
         f"{yr['kept']} of {yr['base']} members" if yr["rate"] is not None else "needs a year of history"),
        ("Industry average", f"{INDUSTRY_YEAR}%", "grey", f"a year · about {INDUSTRY_MONTH:.0f}% a month"),
    ])
    rows = [{"Month": f"{m:%b %Y}", "Members at the start": r["base"], "Kept": r["kept"], "Lost": r["lost"],
             "Kept %": _fmt(r)} for m, r in s["trend"]]
    with st.expander("Month by month"):
        gw.table(rows)
        st.caption("Worked out from membership end dates: a member who renewed counts as kept. Members whose "
                   "membership ended and hasn't been renewed count as lost. This month is counted up to today.")
    if lm["rate"] is not None:
        if lm["rate"] >= INDUSTRY_MONTH:
            st.caption(f"In {s['last_month_label']} you kept members better than the industry average. 👏")
        else:
            st.caption(f"In {s['last_month_label']} you kept fewer members than the industry average. "
                       "The Risk Radar and New members pages show who to reach first.")
