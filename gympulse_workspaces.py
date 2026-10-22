"""GymPulse AI: Risk Radar, Retention Action Centre, Business Insights, Archie.

Pure logic (build_roster, drivers, playbook, kpis, archie_context) is separate
from Streamlit rendering so it can be tested without a database.
"""
from datetime import date, timedelta

import pandas as pd
import streamlit as st

ARCHIE_MODEL = "claude-sonnet-5-5"

ACTIVITY_COLS = [
    "membership_type", "days_since_last_visit", "visits_previous_30_days",
    "visits_last_30_days", "renewal_due_days", "pt_sessions_attended",
]
ACTION_TYPES = ["Personal call", "WhatsApp check-in", "Free PT session",
                "Renewal offer", "Class invite", "Goal review"]
STATUSES = ["To do", "In progress", "Done"]
OUTCOMES = ["Retained", "Cancelled", "No response"]


# ---------------------------------------------------------------- data
def load_roster(supabase, gym_id, assess_fn):
    """Members + activity, scored by the model. Members without activity
    data are returned in `missing` so the UI can ask for it."""
    members = pd.DataFrame(
        supabase.table("members")
        .select("id, full_name, email, phone, fitness_goal")
        .eq("gym_id", gym_id).execute().data or []
    )
    activity = pd.DataFrame(
        supabase.table("member_activity").select("*")
        .eq("gym_id", gym_id).execute().data or []
    )
    return build_roster(members, activity, assess_fn)


def build_roster(members, activity, assess_fn):
    if members.empty:
        return pd.DataFrame(), pd.DataFrame()
    if activity.empty:
        return pd.DataFrame(), members
    df = members.merge(activity, left_on="id", right_on="member_id", how="left")
    has = df["membership_type"].notna()
    missing = df.loc[~has, members.columns]
    scored = df[has].copy()
    if scored.empty:
        return pd.DataFrame(), missing
    scored["monthly_fee"] = pd.to_numeric(scored["monthly_fee"]).fillna(0)
    scored = assess_fn(scored.reset_index(drop=True))
    scored["attendance_change"] = (scored["visits_last_30_days"]
                                   - scored["visits_previous_30_days"])
    scored["revenue_at_risk"] = scored["cancellation_probability"] * scored["monthly_fee"]
    scored["drivers"] = scored.apply(drivers, axis=1)
    scored["suggested_action"] = scored.apply(suggest_action, axis=1)
    return scored.sort_values("cancellation_probability", ascending=False), missing


def load_actions(supabase, gym_id):
    rows = (supabase.table("retention_actions").select("*")
            .eq("gym_id", gym_id).order("created_at", desc=True).execute().data or [])
    return pd.DataFrame(rows)


# ------------------------------------------------------------- logic
def drivers(row):
    """Plain-language reasons a member is flagged (rule-based, transparent)."""
    out = []
    if row["days_since_last_visit"] >= 14:
        out.append(f"{int(row['days_since_last_visit'])} days since last visit")
    change = row["visits_last_30_days"] - row["visits_previous_30_days"]
    if change <= -3:
        out.append("attendance dropping")
    if row["renewal_due_days"] <= 14:
        out.append(f"renews in {int(row['renewal_due_days'])} days")
    if row["pt_sessions_attended"] == 0:
        out.append("no PT sessions")
    if row["membership_type"] == "Monthly":
        out.append("monthly plan (easy to leave)")
    return ", ".join(out) or "no major warning signs"


def suggest_action(row):
    if row["renewal_due_days"] <= 14 and row["risk_category"] != "Low":
        return "Renewal offer"
    if row["days_since_last_visit"] >= 14:
        return "Personal call"
    if row["pt_sessions_attended"] == 0:
        return "Free PT session"
    if row["risk_category"] == "Low":
        return "Goal review"
    return "WhatsApp check-in"


def kpis(roster, actions):
    n = len(roster)
    high = roster[roster["risk_category"] == "High"] if n else roster
    done = actions[actions["status"] == "Done"] if not actions.empty else actions
    retained = int((done["outcome"] == "Retained").sum()) if not done.empty else 0
    decided = int(done["outcome"].isin(["Retained", "Cancelled"]).sum()) if not done.empty else 0
    return {
        "members_scored": n,
        "high": len(high),
        "medium": int((roster["risk_category"] == "Medium").sum()) if n else 0,
        "monthly_revenue": float(roster["monthly_fee"].sum()) if n else 0.0,
        "high_risk_revenue": float(high["monthly_fee"].sum()) if n else 0.0,
        "expected_loss": float(roster["revenue_at_risk"].sum()) if n else 0.0,
        "renewals_30d_at_risk": int(((roster["renewal_due_days"] <= 30)
                                     & (roster["risk_category"] != "Low")).sum()) if n else 0,
        "open_actions": int((actions["status"] != "Done").sum()) if not actions.empty else 0,
        "saves": retained,
        "save_rate": (retained / decided) if decided else None,
        "revenue_saved": float(
            roster.set_index("id").reindex(
                done.loc[done["outcome"] == "Retained", "member_id"]
            )["monthly_fee"].sum()) if retained and n else 0.0,
    }


def archie_context(roster, actions, business_name):
    k = kpis(roster, actions)
    lines = [f"Gym: {business_name}. Members scored: {k['members_scored']}.",
             f"High risk: {k['high']}, Medium: {k['medium']}.",
             f"Monthly revenue: {k['monthly_revenue']:,.0f}; held by high-risk members: "
             f"{k['high_risk_revenue']:,.0f}; expected monthly loss: {k['expected_loss']:,.0f}.",
             f"Renewals in 30 days that are at risk: {k['renewals_30d_at_risk']}.",
             f"Open retention actions: {k['open_actions']}; members saved: {k['saves']}."]
    if len(roster):
        lines.append("Top 10 at-risk members (name | risk% | reasons | suggested action):")
        for _, r in roster.head(10).iterrows():
            lines.append(f"- {r['full_name']} | {r['cancellation_probability']:.0%} | "
                         f"{r['drivers']} | {r['suggested_action']}")
    return "\n".join(lines)


ARCHIE_SYSTEM = (
    "You are Archie, the retention assistant inside GymPulse AI. You help gym "
    "owners keep members. Use ONLY the data provided; if something is not in it, "
    "say so. The risk scores come from a model trained on synthetic data, so call "
    "them estimates, never facts. Be warm, concrete and brief. When asked for a "
    "message to a member, write it ready to send (WhatsApp length, friendly, no "
    "pressure, no mention of 'risk' or 'cancellation')."
)


def archie_reply(history, context):
    """Claude if ANTHROPIC_API_KEY is set; otherwise a rules-based answer."""
    key = st.secrets.get("ANTHROPIC_API_KEY") if hasattr(st, "secrets") else None
    if not key:
        return _offline_reply(history[-1]["content"], context), False
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model=ARCHIE_MODEL, max_tokens=700,
            system=ARCHIE_SYSTEM + "\n\nGYM DATA:\n" + context,
            messages=history[-12:],
        )
        return resp.content[0].text, True
    except Exception as e:
        return f"Archie couldn't reach the AI service ({type(e).__name__}).\n\n" + \
               _offline_reply(history[-1]["content"], context), False


def _offline_reply(question, context):
    return ("I'm running without an AI key, so here is today's snapshot instead:\n\n"
            + context + "\n\nAdd `ANTHROPIC_API_KEY` to your Streamlit secrets to "
            "unlock full answers and ready-to-send member messages.")


# ------------------------------------------------------- rendering
def _money(x):
    return f"{x:,.0f}"


def _need_data(missing, supabase, gym_id):
    st.info("Add attendance data so the model can score your members.")
    if missing.empty:
        return
    with st.form("activity_form"):
        name = st.selectbox("Member", missing["full_name"])
        c1, c2 = st.columns(2)
        mtype = c1.selectbox("Membership type", ["Monthly", "Quarterly", "Annual"])
        fee = c2.number_input("Monthly fee", min_value=0.0, step=500.0)
        d = c1.number_input("Days since last visit", 0, 365, 7)
        prev = c2.number_input("Visits, previous 30 days", 0, 100, 10)
        last = c1.number_input("Visits, last 30 days", 0, 100, 8)
        ren = c2.number_input("Days until renewal", 0, 365, 30)
        pt = c1.number_input("PT sessions attended", 0, 100, 0)
        if st.form_submit_button("Save activity", use_container_width=True):
            mid = missing.loc[missing["full_name"] == name, "id"].iloc[0]
            supabase.table("member_activity").upsert({
                "member_id": mid, "gym_id": gym_id, "membership_type": mtype,
                "monthly_fee": float(fee), "days_since_last_visit": int(d),
                "visits_previous_30_days": int(prev), "visits_last_30_days": int(last),
                "renewal_due_days": int(ren), "pt_sessions_attended": int(pt),
            }).execute()
            st.rerun()
    st.caption(f"{len(missing)} member(s) still need activity data.")


def render_risk_radar(supabase, gym_id, assess_fn):
    st.markdown("## Member Risk Radar")
    st.write("Every member, scored and ranked, with the reasons behind the flag.")
    try:
        roster, missing = load_roster(supabase, gym_id, assess_fn)
    except Exception as e:
        st.error("Couldn't load the radar. Have you run schema.sql?")
        with st.expander("Technical details"):
            st.code(str(e))
        return
    if roster.empty:
        _need_data(missing, supabase, gym_id)
        return

    k = kpis(roster, pd.DataFrame())
    c = st.columns(4)
    c[0].metric("High risk", k["high"])
    c[1].metric("Medium risk", k["medium"])
    c[2].metric("Monthly revenue held by high-risk", _money(k["high_risk_revenue"]))
    c[3].metric("Renewals ≤30d at risk", k["renewals_30d_at_risk"])

    f1, f2, f3 = st.columns([2, 2, 3])
    levels = f1.multiselect("Risk level", ["High", "Medium", "Low"], ["High", "Medium"])
    plans = f2.multiselect("Membership", ["Monthly", "Quarterly", "Annual"],
                           ["Monthly", "Quarterly", "Annual"])
    search = f3.text_input("Search member")
    view = roster[roster["risk_category"].isin(levels) & roster["membership_type"].isin(plans)]
    if search:
        view = view[view["full_name"].str.contains(search, case=False, na=False)]

    st.markdown('<div class="section-label">THE RADAR</div>', unsafe_allow_html=True)
    st.caption("Right = longer absent. Up = higher cancellation estimate.")
    st.scatter_chart(view, x="days_since_last_visit", y="cancellation_probability",
                     color="risk_category", size="monthly_fee", height=320)

    st.markdown('<div class="section-label">PRIORITY LIST</div>', unsafe_allow_html=True)
    show = view[["full_name", "risk_category", "cancellation_probability",
                 "drivers", "suggested_action", "monthly_fee"]].rename(columns={
        "full_name": "Member", "risk_category": "Risk",
        "cancellation_probability": "Probability", "drivers": "Why flagged",
        "suggested_action": "Suggested action", "monthly_fee": "Monthly fee"})
    st.dataframe(show, hide_index=True, use_container_width=True,
                 column_config={"Probability": st.column_config.ProgressColumn(
                     format="%.0f%%", min_value=0, max_value=1)})

    if view.empty:
        return
    st.markdown('<div class="section-label">MEMBER DETAIL</div>', unsafe_allow_html=True)
    pick = st.selectbox("Select a member", view["full_name"], key="radar_pick")
    m = view[view["full_name"] == pick].iloc[0]
    d1, d2, d3 = st.columns(3)
    d1.metric("Cancellation estimate", f"{m['cancellation_probability']:.0%}")
    d2.metric("Attendance change", f"{int(m['attendance_change']):+d}")
    d3.metric("Renews in", f"{int(m['renewal_due_days'])} days")
    st.write(f"**Why flagged:** {m['drivers']}")
    st.write(f"**Suggested:** {m['suggested_action']}")
    if st.button(f"Create action for {pick}", key="radar_create"):
        _create_action(supabase, gym_id, m["id"], m["suggested_action"],
                       m["renewal_due_days"])
        st.success("Added to the Retention Action Centre.")
    st.caption("Estimates come from a model trained on synthetic data. Use them "
               "to prioritise conversations, not to make decisions about members.")


def _create_action(supabase, gym_id, member_id, action_type, renewal_days, note=""):
    due = date.today() + timedelta(days=1 if renewal_days <= 14 else 3)
    supabase.table("retention_actions").insert({
        "gym_id": gym_id, "member_id": member_id, "action_type": action_type,
        "due_date": due.isoformat(), "note": note}).execute()


def render_action_centre(supabase, gym_id, assess_fn):
    st.markdown("## Retention Action Centre")
    st.write("Turn risk into follow-ups, track them, and learn what works.")
    try:
        roster, _ = load_roster(supabase, gym_id, assess_fn)
        actions = load_actions(supabase, gym_id)
    except Exception as e:
        st.error("Couldn't load actions. Have you run schema.sql?")
        with st.expander("Technical details"):
            st.code(str(e))
        return
    if roster.empty:
        st.info("Score your members in the Risk Radar first.")
        return
    names = roster.set_index("id")["full_name"].to_dict()
    k = kpis(roster, actions)
    c = st.columns(3)
    c[0].metric("Open actions", k["open_actions"])
    c[1].metric("Members saved", k["saves"])
    c[2].metric("Save rate", "n/a" if k["save_rate"] is None else f"{k['save_rate']:.0%}")

    open_ids = set(actions.loc[actions["status"] != "Done", "member_id"]) if not actions.empty else set()
    todo = roster[(roster["risk_category"] != "Low") & ~roster["id"].isin(open_ids)]
    st.markdown('<div class="section-label">SUGGESTED TODAY</div>', unsafe_allow_html=True)
    if todo.empty:
        st.success("Every at-risk member already has an open action.")
    else:
        top = todo.head(5)
        for _, r in top.iterrows():
            a, b = st.columns([5, 1])
            a.write(f"**{r['full_name']}** · {r['cancellation_probability']:.0%} · "
                    f"{r['suggested_action']}  \n<small>{r['drivers']}</small>",
                    unsafe_allow_html=True)
            if b.button("Add", key=f"add_{r['id']}"):
                _create_action(supabase, gym_id, r["id"], r["suggested_action"],
                               r["renewal_due_days"])
                st.rerun()
        if len(todo) > 1 and st.button("Add all top 5", use_container_width=True):
            for _, r in top.iterrows():
                _create_action(supabase, gym_id, r["id"], r["suggested_action"],
                               r["renewal_due_days"])
            st.rerun()

    st.markdown('<div class="section-label">YOUR BOARD</div>', unsafe_allow_html=True)
    if actions.empty:
        st.info("No actions yet. Add one from the suggestions above.")
        return
    tabs = st.tabs([f"{s} ({int((actions['status'] == s).sum())})" for s in STATUSES])
    for tab, status in zip(tabs, STATUSES):
        with tab:
            sub = actions[actions["status"] == status]
            if sub.empty:
                st.caption("Nothing here.")
            for _, a in sub.iterrows():
                with st.container(border=True):
                    who = names.get(a["member_id"], "Unknown member")
                    st.write(f"**{who}** · {a['action_type']} · due {a.get('due_date') or '-'}")
                    if status == "Done":
                        st.caption(f"Outcome: {a.get('outcome') or 'not recorded'}")
                        continue
                    n = st.text_input("Note", a.get("note") or "", key=f"n_{a['id']}")
                    x, y = st.columns(2)
                    if status == "To do" and x.button("Start", key=f"s_{a['id']}"):
                        supabase.table("retention_actions").update(
                            {"status": "In progress", "note": n}).eq("id", a["id"]).execute()
                        st.rerun()
                    out = y.selectbox("Outcome", OUTCOMES, key=f"o_{a['id']}")
                    if y.button("Mark done", key=f"d_{a['id']}"):
                        supabase.table("retention_actions").update({
                            "status": "Done", "outcome": out, "note": n,
                            "completed_at": date.today().isoformat()}
                        ).eq("id", a["id"]).execute()
                        st.rerun()


def render_business_insights(supabase, gym_id, assess_fn):
    st.markdown("## Business Insights")
    st.write("What retention is worth, where it leaks, and what's working.")
    try:
        roster, _ = load_roster(supabase, gym_id, assess_fn)
        actions = load_actions(supabase, gym_id)
    except Exception as e:
        st.error("Couldn't load insights. Have you run schema.sql?")
        with st.expander("Technical details"):
            st.code(str(e))
        return
    if roster.empty:
        st.info("Score your members in the Risk Radar first.")
        return
    k = kpis(roster, actions)
    c = st.columns(4)
    c[0].metric("Monthly revenue", _money(k["monthly_revenue"]))
    c[1].metric("Expected monthly loss", _money(k["expected_loss"]))
    c[2].metric("Held by high-risk", _money(k["high_risk_revenue"]))
    c[3].metric("Revenue saved", _money(k["revenue_saved"]))
    st.caption("Expected loss = each member's estimate × their monthly fee. "
               "It is a planning figure from a synthetic-data model, not a forecast.")

    l, r = st.columns(2)
    with l:
        st.markdown('<div class="section-label">RISK MIX</div>', unsafe_allow_html=True)
        mix = roster["risk_category"].value_counts().reindex(["High", "Medium", "Low"]).fillna(0)
        st.bar_chart(mix)
    with r:
        st.markdown('<div class="section-label">REVENUE AT RISK BY PLAN</div>', unsafe_allow_html=True)
        st.bar_chart(roster.groupby("membership_type")["revenue_at_risk"].sum())

    st.markdown('<div class="section-label">RENEWAL PIPELINE</div>', unsafe_allow_html=True)
    bins = pd.cut(roster["renewal_due_days"], [-1, 7, 14, 30, 60, 10_000],
                  labels=["≤7d", "8-14d", "15-30d", "31-60d", "60d+"])
    pipe = roster.groupby(bins, observed=False).agg(
        members=("id", "count"), avg_risk=("cancellation_probability", "mean"),
        fees=("monthly_fee", "sum"))
    pipe["avg_risk"] = pipe["avg_risk"].fillna(0).map("{:.0%}".format)
    st.dataframe(pipe.rename(columns={"members": "Members", "avg_risk": "Avg risk",
                                      "fees": "Monthly fees"}),
                 use_container_width=True)

    st.markdown('<div class="section-label">WHAT WORKS</div>', unsafe_allow_html=True)
    done = actions[actions["status"] == "Done"] if not actions.empty else actions
    if done.empty:
        st.info("Complete some actions with outcomes and this will show which "
                "tactics keep members.")
    else:
        tbl = done.groupby("action_type")["outcome"].agg(
            Done="count", Retained=lambda s: int((s == "Retained").sum()))
        tbl["Save rate"] = (tbl["Retained"] / tbl["Done"]).map("{:.0%}".format)
        st.dataframe(tbl, use_container_width=True)
        if len(done) < 20:
            st.caption("Small sample, so treat these as early signals only.")

    st.markdown('<div class="section-label">TO DO THIS WEEK</div>', unsafe_allow_html=True)
    if k["high"]:
        st.write(f"- Contact the **{k['high']}** high-risk members, starting with "
                 f"the {k['renewals_30d_at_risk']} renewing within 30 days.")
    if k["open_actions"]:
        st.write(f"- Close out **{k['open_actions']}** open actions and record outcomes.")
    if not k["high"] and not k["open_actions"]:
        st.write("- Nothing urgent. Run a goal review with a few Low-risk members.")


ARCHIE_PROMPTS = [
    "Who should I call first today?",
    "Write a WhatsApp message for my most at-risk member",
    "Why is revenue at risk this month?",
    "Give me a 3-step plan for this week",
]


def render_archie(supabase, gym_id, assess_fn, business_name):
    st.markdown("## Archie · your retention assistant")
    st.write("Ask about your members, revenue and follow-ups. Archie reads your "
             "live GymPulse data.")
    try:
        roster, _ = load_roster(supabase, gym_id, assess_fn)
        actions = load_actions(supabase, gym_id)
    except Exception:
        roster, actions = pd.DataFrame(), pd.DataFrame()
    context = archie_context(roster, actions, business_name) if len(roster) \
        else f"Gym: {business_name}. No scored members yet."

    if "archie_msgs" not in st.session_state:
        st.session_state.archie_msgs = []
    cols = st.columns(len(ARCHIE_PROMPTS))
    picked = None
    for col, p in zip(cols, ARCHIE_PROMPTS):
        if col.button(p, key=f"ap_{p}", use_container_width=True):
            picked = p
    for m in st.session_state.archie_msgs:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
    typed = st.chat_input("Ask Archie...")
    question = typed or picked
    if question:
        st.session_state.archie_msgs.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            with st.spinner("Archie is thinking..."):
                reply, live = archie_reply(st.session_state.archie_msgs, context)
            st.markdown(reply)
        st.session_state.archie_msgs.append({"role": "assistant", "content": reply})
    if st.session_state.archie_msgs and st.button("Clear chat"):
        st.session_state.archie_msgs = []
        st.rerun()
    st.caption("Archie can be wrong. Check details before contacting members. "
               "Only your top at-risk members' names and scores are shared with "
               "the AI service.")
