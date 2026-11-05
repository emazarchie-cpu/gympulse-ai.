"""GymPulse AI · Milestones and member of the month.

Milestones come from real check-ins only:
  * visit milestones: 25, 50, 100, 150, 200, 300 and 500 days trained
  * consistency: 12 weeks in a row with 3 or more visits
  * anniversaries: 1, 2, 3... years since joining
The automatic "milestone" email congratulates members (Grow → Automatic
messages). Grow → Celebrate lists recent milestones and suggests a member of
the month, with a ready post for the gym's WhatsApp Status.
"""
from datetime import timedelta

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

VISITS = (25, 50, 100, 150, 200, 300, 500)
STREAK_WEEKS, STREAK_VISITS = 12, 3
RECENT_DAYS = 14          # a milestone is only celebrated if it happened in the last 2 weeks


def _days(ck, mid):
    mine = ck[ck["member_id"] == mid] if len(ck) else ck
    return sorted(set(mine["day"].dt.date)) if len(mine) else []


def milestones(m, ck, today, recent=RECENT_DAYS):
    """[(ref, title, sentence)] reached by one member in the last `recent` days."""
    out = []
    days = _days(ck, m["id"])
    for n in VISITS:
        if len(days) >= n and (today - days[n - 1]).days <= recent:
            out.append((f"ms:visits:{n}", f"{n} visits",
                        f"you've now trained with us {n} times"))
    # weeks in a row with 3+ visits, counting back from last complete week
    if days:
        week_start = today - timedelta(days=today.weekday() + 7)           # Monday of last full week
        per_week = pd.Series(1, index=pd.to_datetime(days)).resample("W-SUN").sum()
        run, wk, first = 0, week_start, None
        while True:
            end = pd.Timestamp(wk + timedelta(days=6))
            if per_week.get(end, 0) >= STREAK_VISITS:
                run, first, wk = run + 1, wk, wk - timedelta(days=7)
            else:
                break
        if run >= STREAK_WEEKS:
            out.append((f"ms:streak:{first.isoformat()}", f"{STREAK_WEEKS} strong weeks",
                        f"you've trained {STREAK_VISITS} or more times a week for {run} weeks in a row"))
    joined = m.get("joined")
    if joined is not None and not pd.isna(joined):
        years = today.year - joined.year - ((today.month, today.day) < (joined.month, joined.day))
        if years >= 1:
            try:
                anniv = joined.replace(year=joined.year + years)
            except ValueError:                                              # 29 February
                anniv = joined.replace(year=joined.year + years, day=28)
            if 0 <= (today - anniv).days <= min(recent, 7):
                out.append((f"ms:year:{years}", f"{years} year{'s' if years != 1 else ''} with us",
                            f"it's {years} year{'s' if years != 1 else ''} since you joined"))
    return out


def milestone_letter(m, title, sentence):
    import gympulse_grow as gg
    biz, owner = gg._biz()
    first = gg._first(m.get("full_name"))
    subject = f"Congratulations, {first}: {title}!"
    body = (f"Hi {first},\n\nWe wanted to celebrate with you: {sentence} at {biz}.\n\n"
            "That kind of commitment is exactly what gets results, and it doesn't go unnoticed. "
            "Thank you for being part of the gym. Here's to the next milestone!\n\n"
            f"{owner}\n{biz}")
    return subject, body, None


def member_of_month(members, ck, month_start):
    """Top 3 for the month: most days trained, then the biggest jump on the month before."""
    nxt = (month_start + timedelta(days=32)).replace(day=1)
    prev = (month_start - timedelta(days=1)).replace(day=1)
    if not len(ck):
        return []
    d = ck.drop_duplicates(["member_id", "day"])
    this = d[(d["day"].dt.date >= month_start) & (d["day"].dt.date < nxt)].groupby("member_id").size()
    before = d[(d["day"].dt.date >= prev) & (d["day"].dt.date < month_start)].groupby("member_id").size()
    by_id = {r["id"]: r for _, r in members.iterrows()}
    rows = [{"m": by_id[mid], "visits": int(n), "before": int(before.get(mid, 0))}
            for mid, n in this.items() if mid in by_id and n >= 4]
    return sorted(rows, key=lambda r: (r["visits"], r["visits"] - r["before"]), reverse=True)[:3]


def status_post(biz, row, month_start):
    first = gw._text(row["m"].get("full_name")).split(" ")[0] or "our member"
    up = row["visits"] - row["before"]
    return (f"🏆 {biz} Member of the Month: {first}!\n\n"
            f"{row['visits']} sessions in {month_start:%B}"
            + (f", {up} more than the month before" if row["before"] and up > 0 else "")
            + f". Consistency like that is what results are made of. Well done, {first}! 👏💪")


def render_celebrate(supabase, gym_id):
    import gympulse_grow as gg
    st.caption("Members who feel seen stay longer. Here are the milestones members reached recently, and a "
               "member of the month you can celebrate on your WhatsApp Status. Turn on \"Celebrate milestones\" in "
               "Automatic messages and GymPulse emails them for you.")
    members = gg._members(supabase, gym_id)
    if members.empty:
        st.info("Add members first.")
        return
    ck = gg._checkins(supabase, gym_id, 1500)
    today = gw.today_local()
    biz = gg._biz()[0]

    st.markdown('<div class="section-label">MEMBER OF THE MONTH</div>', unsafe_allow_html=True)
    this_month = today.replace(day=1)
    last_month = (this_month - timedelta(days=1)).replace(day=1)
    month = st.radio("Month", [last_month, this_month], horizontal=True, key="cel_month",
                     format_func=lambda d: f"{d:%B}" + (" (so far)" if d == this_month else ""),
                     label_visibility="collapsed")
    top = member_of_month(members, ck, month)
    if not top:
        st.info("No one has trained 4 or more times in that month yet.")
    else:
        pick = st.radio("Who?", range(len(top)), horizontal=True, key="cel_pick",
                        format_func=lambda i: f"{['🥇', '🥈', '🥉'][i]} {top[i]['m']['full_name']} · "
                                              f"{top[i]['visits']} visits")
        row = top[pick]
        st.caption("For your WhatsApp Status or members' group. Ask the member first if they're happy to be featured.")
        st.code(status_post(biz, row, month), language=None, wrap_lines=True)
        m = row["m"]
        k = f"cel_mom_{m['id']}_{month:%Y%m}"
        st.session_state.setdefault(k, f"Hi {gg._first(m['full_name'])},\n\nYou're our Member of the Month for "
                                       f"{month:%B}! You trained {row['visits']} times, and we've noticed. Thank you "
                                       f"for the energy you bring to {biz}. Would you be happy for us to "
                                       f"celebrate you on our WhatsApp Status?\n\n{gg._biz()[1]}\n{biz}")
        st.text_area("Message to them", key=k, height=170)
        gg.send_row(k, m, f"cel_mom_send_{m['id']}", f"You're our Member of the Month, {gg._first(m['full_name'])}!",
                    supabase=supabase, gym_id=gym_id)

    st.markdown('<div class="section-label">MILESTONES IN THE LAST 30 DAYS</div>', unsafe_allow_html=True)
    found = []
    for _, m in members.iterrows():
        for ref, title, sentence in milestones(m, ck, today, recent=30):
            found.append({"Member": m["full_name"], "Milestone": title, "_m": m, "_s": sentence, "_t": title})
    if not found:
        st.info("No milestones in the last 30 days yet. They show up here as members reach them.")
        return
    gw.table([{k: v for k, v in f.items() if not k.startswith("_")} for f in found])
