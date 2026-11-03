"""Retention Command Centre: the owner's dashboard.

Revenue first, then who needs attention today and why, then whether the work
is paying off. Verified figures (recorded outcomes, renewals, check-ins) are
always labelled separately from model estimates.
"""
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import streamlit as st

import gympulse_design as gd
import gympulse_workspaces as gw

OUTCOME_WINDOW_DAYS = 30


# ------------------------------------------------------------------ helpers
def _ts(series):
    """Parse timestamps to naive UTC, tolerating blanks."""
    out = pd.to_datetime(series, errors="coerce", utc=True, format="ISO8601")
    return out.dt.tz_localize(None)


def _money(x):
    x = float(x or 0)
    if abs(x) >= 1_000_000:
        return f"{x / 1_000_000:,.1f}m"
    if abs(x) >= 10_000:
        return f"{x / 1_000:,.0f}k"
    return f"{x:,.0f}"


def _plural(n, word, plural=None):
    return f"{n} {word if n == 1 else (plural or word + 's')}"


risk_story = gw.risk_story


def outcomes(roster, actions, days=OUTCOME_WINDOW_DAYS):
    """Verified results from recorded actions and real check-ins."""
    res = {"retained_n": 0, "retained_rev": 0.0, "cancelled_n": 0, "reengaged_n": 0,
           "resolved_n": 0, "save_rate": None, "overdue": 0, "due_today": 0,
           "todo": 0, "doing": 0, "contacted_n": 0, "followup_due": 0}
    if actions is None or actions.empty:
        return res
    a = actions.copy()
    now = pd.Timestamp.utcnow().tz_localize(None)
    today = date.today()
    if "completed_at" not in a.columns:
        a["completed_at"] = None
    if "outcome" not in a.columns:
        a["outcome"] = None
    a["done_at"] = _ts(a["completed_at"])
    open_a = a[a["status"] != "Done"]
    res["todo"] = int((open_a["status"] == "To do").sum())
    res["doing"] = int((open_a["status"] == "In progress").sum())
    due = pd.to_datetime(open_a["due_date"] if "due_date" in open_a.columns
                         else pd.Series(index=open_a.index, dtype=object), errors="coerce").dt.date
    res["overdue"] = int((due < today).sum())
    res["due_today"] = int((due == today).sum())

    if "contacted_at" in a.columns:
        contacted = a["contacted_at"].notna() & (a["contacted_at"].astype(str).str.len() > 0)
    else:
        contacted = pd.Series(False, index=a.index)
    res["contacted_n"] = int((contacted | (a["status"] == "Done")).sum())
    res["followup_due"] = int(sum(gw.action_stage(r) == "Follow-up due"
                                  for r in open_a.to_dict("records")))
    done = a[(a["status"] == "Done") & (a["done_at"] >= now - pd.Timedelta(days=days))]
    res["resolved_n"] = len(done)
    kept = done[done["outcome"] == "Retained"].drop_duplicates("member_id")
    res["retained_n"] = len(kept)
    res["cancelled_n"] = int((done["outcome"] == "Cancelled").sum())
    decided = res["retained_n"] + res["cancelled_n"]
    res["save_rate"] = res["retained_n"] / decided if decided else None
    if not roster.empty and len(kept):
        fees = roster.set_index("id")["monthly_fee"]
        res["retained_rev"] = float(fees.reindex(kept["member_id"]).fillna(0).sum())

    # Re-engaged: checked in again after the play was closed (from real attendance)
    if not roster.empty and len(done):
        last_visit = now - pd.to_timedelta(
            roster.set_index("id")["days_since_last_visit"].astype(float), unit="D")
        d = done[done["outcome"] != "Cancelled"].dropna(subset=["done_at"]) \
            .drop_duplicates("member_id", keep="first")
        lv = last_visit.reindex(d["member_id"]).values
        res["reengaged_n"] = int((pd.Series(lv, dtype="datetime64[ns]")
                                  >= d["done_at"].dt.normalize().values).sum())
    return res


def renewal_watch(roster, horizon=30):
    """Members renewing soon who are also attending less or flagged at risk."""
    if roster.empty:
        return roster
    soon = roster[(roster["renewal_due_days"] >= -7) & (roster["renewal_due_days"] <= horizon)]
    return soon[(soon["attendance_change"] < 0) | (soon["risk_category"] != "Low")] \
        .sort_values(["renewal_due_days", "cancellation_probability"], ascending=[True, False])


def play_performance(actions):
    if actions is None or actions.empty:
        return []
    done = actions[actions["status"] == "Done"]
    rows = []
    for play, g in done.groupby("action_type"):
        out = g["outcome"].fillna("").astype(str) if "outcome" in g.columns else pd.Series(dtype=str)
        kept, lost = int((out == "Retained").sum()), int((out == "Cancelled").sum())
        rows.append({"play": play, "kept": kept, "decided": kept + lost, "total": len(g)})
    rows.sort(key=lambda r: (r["decided"], r["kept"]), reverse=True)
    return rows


def daily_brief(roster, actions, res, watch, need):
    """Archie's morning brief, built only from the data on screen."""
    lines = []
    declining = roster[roster["attendance_change"] <= -3] if not roster.empty else roster
    if len(declining):
        renewing = declining[declining["renewal_due_days"].between(0, 30)]
        line = f"<b>{_plural(len(declining), 'member')}</b> {'is' if len(declining) == 1 else 'are'} attending less than last month"
        if len(renewing):
            line += (f", and <b>{len(renewing)}</b> of them renew within 30 days "
                     f"({_money(renewing['monthly_fee'].sum())} a month). Call those first.")
        else:
            line += ". None renew in the next 30 days, so a friendly check-in is enough."
        lines.append(line)
    if len(need):
        top = need.iloc[0]
        lines.append(f"Top priority: <b>{gw._esc(top['full_name'])}</b>. "
                     f"{gw._esc(risk_story(top)['why'].capitalize())}.")
    if res["overdue"]:
        lines.append(f"<b>{_plural(res['overdue'], 'follow-up')}</b> {'is' if res['overdue'] == 1 else 'are'} overdue in the Action Centre.")
    if res["retained_n"]:
        lines.append(f"Last 30 days: <b>{_plural(res['retained_n'], 'member')} kept</b> after a play, "
                     f"worth {_money(res['retained_rev'])} a month (recorded outcomes).")
    perf = [p for p in play_performance(actions) if p["decided"] >= 2]
    if perf:
        best = max(perf, key=lambda p: p["kept"] / p["decided"])
        lines.append(f"Best play so far: <b>{gw._esc(best['play'])}</b> "
                     f"({best['kept']} of {best['decided']} kept). Small sample, early signal.")
    if not lines:
        lines.append("Everyone looks steady. A good day for goal reviews with loyal members.")
    return lines[:4]


# ------------------------------------------------------------------ actions
def _start_play(supabase, gym_id, member_id, play, renew, note):
    try:
        if gw._has_open_action(supabase, member_id):
            st.session_state["cc_flash"] = ("info", "This member already has an open play in the Action Centre.")
            return
        gw._create_action(supabase, gym_id, member_id, play, renew, note=note)
        gw.bump_data_version()
        st.session_state["cc_flash"] = ("success", f"{play} added to the Action Centre.")
    except Exception as e:
        st.session_state["cc_flash"] = ("error", f"Could not start the play: {e}")


def _ask_archie(question):
    st.session_state["archie_pending"] = question
    st.session_state["navigate_to"] = "Archie"


# ------------------------------------------------------------------ view
def _kpi(label, value, hint, tone, tag=""):
    return (f'<div class="cc-kpi" style="--tone:{tone}"><div class="cc-kpi-head">'
            f'<span class="cc-kpi-label">{label}</span>{tag}</div>'
            f'<div class="cc-kpi-value">{value}</div><div class="cc-kpi-hint">{hint}</div></div>')


def _priority_row(supabase, gym_id, r, i, mobile):
    story = risk_story(r)
    chips = (gw.risk_chip(r["risk_category"], r["cancellation_probability"])
             + gw.chip(f"{_money(r['monthly_fee'])}/mo", "grey"))
    body = (f'<dl class="cc-story"><dt>Why</dt><dd>{gw._esc(story["why"])}</dd>'
            f'<dt>When</dt><dd>{gw._esc(story["when"])}</dd>'
            f'<dt>Next</dt><dd>{story["next"]}</dd></dl>')
    note = f"Why: {story['why']}. When: {story['when']}."
    args = (supabase, gym_id, r["id"], story["play"], int(r["renewal_due_days"]), note)
    if mobile:
        with st.container(border=True, key=f"card_cc_m_{r['id']}"):
            gw._md('<div style="display:flex;align-items:center;gap:12px;">'
                   + gw.avatar_html(r["full_name"], r.get("photo"), 44)
                   + f'<div style="min-width:0"><div class="cc-pri-name">{gw._esc(r["full_name"])}</div>'
                   + f'<div class="cc-chips">{chips}</div></div></div>' + body)
            a, b = st.columns(2)
            a.button(f"Start {story['play'].lower()}", key=f"cc_play_m_{r['id']}", type="primary",
                     on_click=_start_play, args=args, use_container_width=True)
            b.button("Profile", key=f"cc_prof_m_{r['id']}", on_click=gw.open_profile,
                     args=(r["id"], "Dashboard"), use_container_width=True)
        return
    c = st.columns([0.5, 3.7, 1.5], vertical_alignment="top")
    gw._md(gw.avatar_html(r["full_name"], r.get("photo"), 42, "row-tight"), c[0])
    with c[1]:
        gw._md(f'<div class="cc-pri-name">{i}. {gw._esc(r["full_name"])}</div>'
               f'<div class="cc-chips" style="margin-top:4px">{chips}</div>{body}')
    with c[2]:
        st.button("Start play", key=f"cc_play_{r['id']}", type="primary", icon=":material/bolt:",
                  on_click=_start_play, args=args, use_container_width=True,
                  help=f"Adds a {story['play']} to the Action Centre")
        st.button("Profile", key=f"cc_prof_{r['id']}", icon=":material/person:",
                  on_click=gw.open_profile, args=(r["id"], "Dashboard"), use_container_width=True)
    st.markdown('<div style="height:1px;background:rgba(255,255,255,0.06);margin:6px 0 10px"></div>',
                unsafe_allow_html=True)


def render_command_centre(supabase, gym_id, assess_fn, greeting, user_name, business_name):
    try:
        roster, missing = gw.load_roster(supabase, gym_id, assess_fn)
        actions = gw.load_actions(supabase, gym_id, include_archived=True)
    except Exception:
        roster, missing, actions = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    mobile = gw._mobile()
    today = gw.today_local()
    ck_ids = set()
    try:
        ck = gw.load_checkins(supabase, gym_id)
        if ck is not None and not ck.empty:
            ck_ids = set(ck["member_id"])
    except Exception:
        pass
    from_ck = int(roster["id"].isin(ck_ids).sum()) if not roster.empty else 0
    if roster.empty or not from_ck:
        source = '<span class="gp-tag">Typed-in attendance</span>'
    elif from_ck == len(roster):
        source = '<span class="gp-tag live">All from live check-ins</span>'
    else:
        source = f'<span class="gp-tag live">{from_ck} of {len(roster)} from check-ins</span>'

    if roster.empty:
        if missing is not None and len(missing):
            st.info(f"{_plural(len(missing), 'member')} registered without a plan or fee. Add their "
                    "membership details on the Risk Radar (Data tools) and they'll be scored.")
        gw._md(f"""<div class="cc-hero"><div class="cc-hero-top"><div>
            <div class="cc-eyebrow">Retention command centre · {today:%A %d %B}</div>
            <div class="cc-hello">{gw._esc(greeting)}, {gw._esc(user_name)}</div>
            <div class="cc-sub">Let's set up <b>{gw._esc(business_name)}</b>. Three steps and GymPulse AI
              starts telling you who needs you, and why.</div></div></div>{gd.PULSE_SVG}</div>""")
        gw._md("""<div class="lx-loop">
          <div class="lx-card"><div class="lx-num">STEP 1</div><h4>Add your members</h4>
            <p>Name, plan, fee and renewal date. One at a time or from a spreadsheet.</p></div>
          <div class="lx-card"><div class="lx-num">STEP 2</div><h4>Check members in</h4>
            <p>Use the front-desk check-in. Each visit feeds the Risk Radar automatically.</p></div>
          <div class="lx-card"><div class="lx-num">STEP 3</div><h4>Run your first play</h4>
            <p>Your dashboard ranks who to contact today and drafts the message.</p></div>
          <div class="lx-card"><div class="lx-num">THEN</div><h4>Watch the revenue</h4>
            <p>Record outcomes and see the membership revenue your team kept.</p></div></div>""")
        a, b, _ = st.columns([1, 1, 2])
        a.button("Add members", key="cc_start_members", type="primary", icon=":material/group_add:",
                 on_click=gw._go, args=("Member Management",), use_container_width=True)
        b.button("Open check-in", key="cc_start_ck", icon=":material/how_to_reg:",
                 on_click=gw._go, args=("Check-in",), use_container_width=True)
        return

    live = actions[actions["archived_at"].isna()] if "archived_at" in actions.columns else actions
    k = gw.kpis(roster, live)
    res = outcomes(roster, actions)
    need = gw.members_to_contact(roster, actions)
    watch = renewal_watch(roster)
    high_n = int((roster["risk_category"] == "High").sum())

    # ---- hero
    headline = (f"<b>{_plural(len(need), 'member')}</b> need{'s' if len(need) == 1 else ''} you today"
                if len(need) else "Nobody needs urgent attention today")
    extra = []
    if len(watch):
        extra.append(f"<b>{len(watch)}</b> at-risk renewal{'s' if len(watch) != 1 else ''} in the next 30 days")
    if res["overdue"]:
        extra.append(f"<b>{res['overdue']}</b> overdue follow-up{'s' if res['overdue'] != 1 else ''}")
    sub = headline + (" · " + " · ".join(extra) if extra else "") + "."
    gw._md(f"""<div class="cc-hero"><div class="cc-hero-top"><div>
        <div class="cc-eyebrow">Retention command centre · {today:%A %d %B}</div>
        <div class="cc-hello">{gw._esc(greeting)}, {gw._esc(user_name)}</div>
        <div class="cc-sub">{sub}</div></div>
        <div class="cc-meta">{source}<span class="gp-tag">{_plural(len(roster), 'member')} tracked</span></div>
        </div>{gd.PULSE_SVG}</div>""")

    flash = st.session_state.pop("cc_flash", None)
    if flash:
        getattr(st, flash[0], st.info)(flash[1])
    if missing is not None and len(missing):
        m1, m2 = st.columns([4, 1.2], vertical_alignment="center")
        m1.warning(f"{_plural(len(missing), 'member')} {'has' if len(missing) == 1 else 'have'} no plan or fee "
                   "yet, so GymPulse can't score them. Add their membership details to include them.")
        m2.button("Add details", key="cc_missing", icon=":material/edit:", on_click=gw._go,
                  args=("Risk Radar",), use_container_width=True)

    # ---- revenue first
    rate = "n/a" if res["save_rate"] is None else f"{res['save_rate']:.0%}"
    gw._md('<div class="cc-kpis">'
           + _kpi("Revenue at risk", _money(k["expected_loss"]) + "<small>/mo</small>",
                  f"{high_n} high-risk members hold {_money(k['high_risk_revenue'])}/mo in fees",
                  "#FF6B6B", '<span class="gp-tag est">Estimate</span>')
           + _kpi("Revenue retained", _money(res["retained_rev"]) + "<small>/mo</small>",
                  f"{_plural(res['retained_n'], 'member')} kept after a play · last 30 days",
                  "#B7F34A", '<span class="gp-tag ok">Verified</span>')
           + _kpi("Re-engaged", str(res["reengaged_n"]),
                  f"Checked in again after a play · save rate {rate}",
                  "#35D6ED", '<span class="gp-tag ok">Check-ins</span>')
           + _kpi("Follow-ups", str(res["todo"] + res["doing"]),
                  f"{res['overdue']} overdue · {res['followup_due']} follow-ups due",
                  "#FFC44D" if res["overdue"] else "#9AA8BD")
           + "</div>")
    st.caption("Estimates come from an experimental model. Verified figures only count recorded "
               "outcomes and real check-ins.")

    # ---- today's priorities + brief
    left, right = st.columns([1.6, 1], gap="medium")
    with left:
        st.markdown('<div class="section-label">TODAY\'S PRIORITIES</div>', unsafe_allow_html=True)
        if need.empty:
            st.success("No one needs a new play right now. Open plays are in the Action Centre.")
        else:
            ranked = need.assign(
                _urgent=(need["risk_category"] == "High") & (need["renewal_due_days"] <= 30),
                _value=need["cancellation_probability"] * need["monthly_fee"],
            ).sort_values(["_urgent", "_value"], ascending=False)
            show = st.session_state.get("cc_show", 4)
            with st.container(border=not mobile, key="cc_priorities"):
                for i, (_, r) in enumerate(ranked.head(show).iterrows(), 1):
                    _priority_row(supabase, gym_id, r, i, mobile)
                a, b = st.columns(2)
                if len(ranked) > show:
                    a.button(f"Show {min(4, len(ranked) - show)} more", key="cc_more", type="tertiary",
                             on_click=gw._bump, args=("cc_show", 4, 4))
                b.button("Open the Risk Radar", key="cc_radar", type="tertiary",
                         icon=":material/radar:", on_click=gw._go, args=("Risk Radar",))
    with right:
        st.markdown('<div class="section-label">ARCHIE\'S BRIEF</div>', unsafe_allow_html=True)
        bullets = "".join(f"<li>{b}</li>" for b in daily_brief(roster, actions, res, watch, need))
        gw._md(f"""<div class="cc-brief"><div class="cc-brief-head"><div class="cc-brief-orb"></div>
            <div><div class="cc-brief-title">Good to know today</div>
            <div class="cc-brief-sub">From your member records, check-ins and recorded outcomes</div></div></div>
            <ul>{bullets}</ul></div>""")
        for q in ("What should my staff prioritise today?", "Which renewals are at risk this month?"):
            st.button(q, key=f"cc_ask_{q[:12]}", icon=":material/auto_awesome:",
                      on_click=_ask_archie, args=(q,), use_container_width=True)

        st.markdown('<div class="section-label">RENEWAL WATCH · 30 DAYS</div>', unsafe_allow_html=True)
        with st.container(border=True, key="cc_watch"):
            if watch.empty:
                gw._md('<div class="cc-empty">No at-risk renewals in the next 30 days.</div>')
            else:
                gw._md(f'<div class="cc-empty"><b style="color:#F4F7FB">{_plural(len(watch), "member")}</b> '
                       f'renewing soon {"is" if len(watch) == 1 else "are"} attending less or at risk, '
                       f'worth <b style="color:#F4F7FB">{_money(watch["monthly_fee"].sum())}/mo</b>.</div>')
                for _, r in watch.head(4).iterrows():
                    d = int(r["renewal_due_days"])
                    when = "lapsed" if d < 0 else "today" if d == 0 else f"in {d}d"
                    c = st.columns([3, 1.4], vertical_alignment="center")
                    c[0].button(str(r["full_name"]), key=f"cc_w_{r['id']}", type="tertiary",
                                on_click=gw.open_profile, args=(r["id"], "Dashboard"))
                    gw._md(gw.chip(f"Renews {when}", "red" if d <= 7 else "amber"), c[1])
                st.button("Open Payments & Renewals", key="cc_pay", type="tertiary",
                          on_click=gw._go, args=("Payments & Renewals",))

    # ---- the retention loop
    st.markdown('<div class="section-label">RETENTION LOOP · LAST 30 DAYS</div>', unsafe_allow_html=True)
    flagged = int((roster["risk_category"] != "Low").sum())
    started = res["todo"] + res["doing"] + res["resolved_n"]
    steps = [("Detected", flagged, "Members flagged medium or high risk", flagged),
             ("Started", started, "Plays started or finished", started),
             ("Contacted", res["contacted_n"], f"Members reached · {res['followup_due']} follow-ups due",
              res["contacted_n"]),
             ("Kept", res["retained_n"], f"Members retained · {_money(res['retained_rev'])}/mo", res["retained_n"])]
    top = max(1, flagged, started)
    gw._md('<div class="cc-loop">' + "".join(
        f'<div class="cc-step"><div class="cc-step-n">{n:02d} · {lab}</div>'
        f'<div class="cc-step-v">{v}</div><div class="cc-step-l">{hint}</div>'
        f'<div class="cc-step-bar"><span style="width:{min(100, round(bar / top * 100))}%"></span></div></div>'
        for n, (lab, v, hint, bar) in enumerate(steps, 1)) + "</div>")

    # ---- what works
    a, b = st.columns([1.6, 1], gap="medium")
    with a:
        st.markdown('<div class="section-label">WHICH PLAYS WORK</div>', unsafe_allow_html=True)
        perf = play_performance(actions)
        with st.container(border=True, key="cc_perf"):
            if not perf:
                gw._md('<div class="cc-empty">Close a few plays with an outcome (Retained, Cancelled or '
                       'No response) and this shows which ones keep members.</div>')
            else:
                gw._md("".join(
                    f'<div class="cc-play"><div class="cc-play-name">{gw._esc(p["play"])}</div>'
                    f'<div class="cc-play-bar"><span style="width:{round(p["kept"] / p["decided"] * 100) if p["decided"] else 0}%"></span></div>'
                    f'<div class="cc-play-rate">{p["kept"]}/{p["decided"] or "–"}</div></div>'
                    for p in perf[:6]))
                gw._md('<div class="cc-brief-foot">Kept ÷ (kept + cancelled). "No response" is left out '
                       'because the result is unknown. Small samples are early signals only.</div>')
    with b:
        st.markdown('<div class="section-label">SHORTCUTS</div>', unsafe_allow_html=True)
        tiles = [("Front-desk check-in", "Check-in", ":material/how_to_reg:"),
                 ("Action Centre", "Action Centre", ":material/task_alt:"),
                 ("Members", "Member Management", ":material/group:"),
                 ("Business Insights", "Business Insights", ":material/insights:")]
        for row in (tiles[:2], tiles[2:]):
            cols = st.columns(2)
            for col, (label, page, icon) in zip(cols, row):
                gw._ibtn(col, label, icon, key=f"qa_{page}", on_click=gw._go, args=(page,),
                         use_container_width=True)
