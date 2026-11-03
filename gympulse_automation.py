"""Phase 4: intelligent automation, with the owner in control.

* Risk-triggered rules create retention plays for the team to review.
  Automation never sends a message to a member: every message still needs a
  person to press send.
* Staff assignment and workload.
* A weekly retention report the owner can download or email to themselves.

Rules and staff live in the owner's profile settings, so nothing here needs a
new table. sql/phase4_automation.sql adds assigned_to / created_by columns to
plays; before it runs, those details are written into the play's note.
"""
import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

RUN_EVERY_SECONDS = 600
AUTO_PREFIX = "Auto rule"

TRIGGERS = {
    "high_risk": {"label": "A member becomes high risk",
                  "help": "Risk level High on the Risk Radar.", "param": None},
    "renewal_fading": {"label": "Renewal is close and attendance is dropping",
                       "help": "Renews within the number of days, and visits fell versus the previous month.",
                       "param": ("Renews within (days)", 14)},
    "absent": {"label": "No check-in for a number of days",
               "help": "Days since last visit, from check-ins.", "param": ("Days without a visit", 14)},
    "lapsed": {"label": "Membership lapsed recently",
               "help": "Membership ended within the number of days.", "param": ("Lapsed within (days)", 14)},
}

SUGGESTED = "__suggested__"     # use each member's own suggested play

DEFAULT_RULES = [
    {"id": "r_renew", "trigger": "renewal_fading", "play": "Renewal offer", "enabled": True, "param": 14},
    {"id": "r_high", "trigger": "high_risk", "play": SUGGESTED, "enabled": True, "param": None},
    {"id": "r_absent", "trigger": "absent", "play": "WhatsApp check-in", "enabled": False, "param": 14},
    {"id": "r_lapsed", "trigger": "lapsed", "play": "Personal call", "enabled": False, "param": 14},
]


# ------------------------------------------------------------------ settings
def _settings(profile=None):
    p = profile if isinstance(profile, dict) else (st.session_state.get("user_profile") or {})
    return dict(p.get("settings") or {})


def automation_settings(profile=None):
    s = _settings(profile)
    auto = dict(s.get("automation") or {})
    rules = auto.get("rules") or [dict(r) for r in DEFAULT_RULES]
    return {"enabled": bool(auto.get("enabled", False)),
            "daily_cap": int(auto.get("daily_cap", 10)),
            "rules": rules}


def staff_list(profile=None):
    return [n for n in (_settings(profile).get("staff") or []) if str(n).strip()]


# ------------------------------------------------------------------ engine
def matches(rule, roster):
    """Members that meet a rule's trigger right now."""
    if roster.empty:
        return roster
    t, n = rule.get("trigger"), int(rule.get("param") or 14)
    if t == "high_risk":
        return roster[roster["risk_category"] == "High"]
    if t == "renewal_fading":
        return roster[(roster["renewal_due_days"].between(0, n)) & (roster["attendance_change"] < 0)]
    if t == "absent":
        return roster[roster["days_since_last_visit"] >= n]
    if t == "lapsed":
        if "membership_end" not in roster.columns:
            return roster.iloc[0:0]
        end = pd.to_datetime(roster["membership_end"], errors="coerce")
        days = (pd.Timestamp(gw.today_local()) - end).dt.days
        return roster[(days > 0) & (days <= n)]
    return roster.iloc[0:0]


def _created_today_by_rules(actions):
    if actions is None or actions.empty:
        return 0
    created = pd.to_datetime(actions["created_at"], errors="coerce", utc=True, format="ISO8601")
    today = pd.Timestamp(gw.today_local()).tz_localize(gw.APP_TZ).tz_convert("UTC")
    by_rule = actions["note"].fillna("").astype(str).str.startswith(AUTO_PREFIX)
    if "created_by" in actions.columns:
        by_rule |= actions["created_by"].fillna("").astype(str).str.startswith("rule")
    return int((by_rule & (created >= today)).sum())


def plan_automations(roster, actions, settings):
    """What the rules would create now: a list of (member row, rule). Pure, no writes."""
    if not settings["enabled"] or roster.empty:
        return []
    room = max(0, settings["daily_cap"] - _created_today_by_rules(actions))
    if not room:
        return []
    pool = gw.members_to_contact(roster, actions, include_low=True)
    out, taken = [], set()
    for rule in settings["rules"]:
        if not rule.get("enabled"):
            continue
        hit = matches(rule, pool)
        hit = hit.sort_values("cancellation_probability", ascending=False)
        for _, r in hit.iterrows():
            if r["id"] in taken:
                continue
            out.append((r, rule))
            taken.add(r["id"])
            if len(out) >= room:
                return out
    return out


def _assign_staff(rule, staff):
    who = rule.get("assign_to") or ""
    return who if who in staff else ""


def run_automations(supabase, gym_id, roster, actions, force=False):
    """Create plays for members who meet an enabled rule. Throttled per session.
    Returns the number of plays created."""
    settings = automation_settings()
    if not settings["enabled"]:
        return 0
    last = st.session_state.get("_auto_last", 0)
    if not force and time.time() - last < RUN_EVERY_SECONDS:
        return 0
    st.session_state["_auto_last"] = time.time()
    staff = staff_list()
    made = 0
    for r, rule in plan_automations(roster, actions, settings):
        label = TRIGGERS.get(rule["trigger"], {}).get("label", "rule")
        note = f"{AUTO_PREFIX} · {label}. {gw.story_text(r)}"
        try:
            if gw._has_open_action(supabase, r["id"]):
                continue
            play = r["suggested_action"] if rule["play"] == SUGGESTED else rule["play"]
            gw._create_action(supabase, gym_id, r["id"], play, int(r["renewal_due_days"]),
                              note=note)
            made += 1
        except Exception:
            continue
        who = _assign_staff(rule, staff)
        extra = {"created_by": f"rule:{rule['id']}"}
        if who:
            extra["assigned_to"] = who
        row = gw.open_action_for(supabase, r["id"])
        if row is None:
            continue
        try:
            supabase.table("retention_actions").update(extra).eq("id", row["id"]).execute()
        except Exception:
            if who:          # columns not added yet: keep the assignment in the note
                try:
                    supabase.table("retention_actions").update(
                        {"note": note + f" · Assigned to {who}"}).eq("id", row["id"]).execute()
                except Exception:
                    pass
    if made:
        gw.bump_data_version()
    return made


# ------------------------------------------------------------------ staff
def assigned_to(a):
    v = a.get("assigned_to")
    if not gw._blank(v):
        return str(v)
    note = gw._text(a.get("note"))
    if "Assigned to " in note:
        return note.rsplit("Assigned to ", 1)[1].split(" ·")[0].strip()
    return ""


def assign(supabase, action_id, who, note=""):
    try:
        supabase.table("retention_actions").update({"assigned_to": who or None}) \
            .eq("id", action_id).execute()
        return True
    except Exception:
        base = note.split(" · Assigned to ")[0] if note else ""
        supabase.table("retention_actions").update(
            {"note": (base + " · " if base else "") + (f"Assigned to {who}" if who else "")}) \
            .eq("id", action_id).execute()
        return False


def workload(actions, staff):
    rows = []
    live = actions[actions["status"] != "Done"] if not actions.empty else actions
    if "archived_at" in live.columns:
        live = live[live["archived_at"].isna()]
    recs = live.to_dict("records") if not live.empty else []
    for who in staff + [""]:
        mine = [a for a in recs if assigned_to(a) == who]
        if who == "" and not mine:
            continue
        stages = [gw.action_stage(a) for a in mine]
        overdue = 0
        for a in mine:
            try:
                if date.fromisoformat(str(a.get("due_date"))[:10]) < date.today():
                    overdue += 1
            except ValueError:
                pass
        rows.append({"who": who or "Unassigned", "open": len(mine), "overdue": overdue,
                     "follow_up_due": stages.count("Follow-up due")})
    return rows


def render_workload(actions):
    staff = staff_list()
    if not staff:
        return
    rows = workload(actions, staff)
    st.markdown('<div class="section-label">TEAM WORKLOAD</div>', unsafe_allow_html=True)
    cols = st.columns(min(len(rows), 4) or 1)
    for i, r in enumerate(rows):
        tone = "red" if r["overdue"] else "amber" if r["follow_up_due"] else "lime"
        hint = f"{r['overdue']} overdue · {r['follow_up_due']} follow-ups due"
        gw._md(gw.kpi_card(r["who"], f"{r['open']} open", tone, hint), cols[i % len(cols)])


def render_assign_control(supabase, a, prefix):
    staff = staff_list()
    if not staff or a.get("status") == "Done":
        who = assigned_to(a)
        if who:
            st.caption(f"Assigned to {who}")
        return
    current = assigned_to(a)
    options = [""] + staff
    pick = st.selectbox("Assigned to", options, index=options.index(current) if current in options else 0,
                        format_func=lambda n: n or "Unassigned", key=f"{prefix}_as_{a['id']}")
    if pick != current:
        assign(supabase, a["id"], pick, gw._text(a.get("note")))
        gw.bump_data_version()
        st.rerun()


# ------------------------------------------------------------------ settings UI
def render_automation_settings(save, profile):
    s = dict(profile.get("settings") or {})
    cfg = automation_settings(profile)
    st.markdown("**Your team**")
    staff_txt = st.text_area("Staff who follow up with members (one name per line)",
                             value="\n".join(staff_list(profile)), height=110,
                             placeholder="e.g.\nCoach Femi\nFront desk: Ada")
    st.markdown("**Automation**")
    st.info("Automation only creates plays on your Action Centre board for your team to review. "
            "It never sends a message to a member: every message still needs someone to press send, "
            "and offers only use the terms you type in.")
    enabled = st.toggle("Create plays automatically from these rules", value=cfg["enabled"])
    cap = st.number_input("Most plays the rules may create per day", 1, 50, cfg["daily_cap"])
    staff = [n.strip() for n in staff_txt.splitlines() if n.strip()]
    plays = [SUGGESTED] + gw.ACTION_TYPES
    play_label = lambda p: "Each member's suggested play" if p == SUGGESTED else p
    new_rules = []
    for rule in cfg["rules"]:
        t = TRIGGERS.get(rule["trigger"])
        if not t:
            continue
        with st.container(border=True, key=f"card_rule_{rule['id']}"):
            on = st.toggle(t["label"], value=bool(rule.get("enabled")), key=f"ru_on_{rule['id']}",
                           help=t["help"])
            c1, c2, c3 = st.columns(3)
            param = rule.get("param")
            if t["param"]:
                param = c1.number_input(t["param"][0], 1, 120, int(param or t["param"][1]),
                                        key=f"ru_p_{rule['id']}")
            play = c2.selectbox("Play to create", plays, format_func=play_label,
                                index=plays.index(rule["play"]) if rule["play"] in plays else 0,
                                key=f"ru_play_{rule['id']}")
            opts = [""] + staff
            who = rule.get("assign_to") or ""
            assign_to = c3.selectbox("Assign to", opts, index=opts.index(who) if who in opts else 0,
                                     format_func=lambda n: n or "Unassigned", key=f"ru_as_{rule['id']}")
        new_rules.append({**rule, "enabled": on, "param": param, "play": play, "assign_to": assign_to})
    if st.button("Save team and automation", key="settings_auto", type="primary"):
        save({"settings": {**s, "staff": staff,
                           "automation": {"enabled": enabled, "daily_cap": int(cap), "rules": new_rules}}},
             "Team and automation saved.")


# ------------------------------------------------------------------ weekly report
def weekly_report_data(supabase, gym_id, roster, actions, days=7):
    """Everything the weekly report says, from recorded data and labelled estimates."""
    import gympulse_command as gc
    import gympulse_revenue as gr
    today = gw.today_local()
    since = pd.Timestamp(today - timedelta(days=days)).tz_localize(gw.APP_TZ).tz_convert("UTC")
    a = actions.copy() if actions is not None else pd.DataFrame()

    def _in_window(col):
        if a.empty or col not in a.columns:
            return pd.Series(False, index=a.index)
        return pd.to_datetime(a[col], errors="coerce", utc=True, format="ISO8601") >= since

    closed = a[_in_window("completed_at")] if not a.empty else a
    out = closed["outcome"].fillna("") if len(closed) and "outcome" in closed.columns else pd.Series(dtype=str)
    need = gw.members_to_contact(roster, actions) if not roster.empty else roster
    staff = staff_list()
    return {
        "start": today - timedelta(days=days), "end": today,
        "members": len(roster),
        "high": int((roster["risk_category"] == "High").sum()) if not roster.empty else 0,
        "at_risk_rev": float(roster["revenue_at_risk"].sum()) if not roster.empty else 0.0,
        "started": int(_in_window("created_at").sum()),
        "contacted": int(_in_window("contacted_at").sum()),
        "closed": len(closed), "kept": int((out == "Retained").sum()), "lost": int((out == "Cancelled").sum()),
        "res": gc.outcomes(roster, actions),
        "rev": gr.revenue_summary(supabase, gym_id, roster, days=days),
        "need": [(r["full_name"], gw.risk_story(r)) for _, r in need.head(8).iterrows()],
        "team": workload(actions, staff) if staff and actions is not None and not actions.empty else [],
    }


def _plain(html):
    import re
    return re.sub("<[^>]+>", "", html)


def weekly_report(supabase, gym_id, roster, actions, business_name, days=7):
    """The weekly report as plain text (email body and on-screen preview)."""
    d = weekly_report_data(supabase, gym_id, roster, actions, days)
    rev, res = d["rev"], d["res"]
    lines = [f"# {business_name} · Weekly retention report",
             f"{d['start']:%d %b} to {d['end']:%d %b %Y}", "",
             "## Members",
             f"- Members tracked: {d['members']}",
             f"- High risk now: {d['high']} (estimate)",
             f"- Revenue at risk: {d['at_risk_rev']:,.0f} a month (estimate)",
             "", "## Retention work this week (recorded)",
             f"- Plays started: {d['started']}",
             f"- Members contacted: {d['contacted']}",
             f"- Plays closed: {d['closed']} · kept {d['kept']} · cancelled {d['lost']}",
             f"- Overdue follow-ups now: {res['overdue']}",
             "", "## Revenue this week (recorded)"]
    if rev["source"] == "payments":
        lines += [f"- Collected: {rev['collected']:,.0f} from {rev['renewals_n']} renewal payment(s)",
                  f"- Credited to plays: {rev['retained_by_plays']:,.0f} ({rev['credited_n']} renewal(s))",
                  f"- Recovered from lapsed members: {rev['recovered']:,.0f}"]
    if rev["renewal_rate"] is not None:
        lines.append(f"- Renewal rate: {rev['renewal_rate']:.0%} ({rev['renewed']} renewed, {rev['lapsed']} lapsed)")
    if d["need"]:
        lines += ["", "## Who needs you next week"]
        for name, story in d["need"][:5]:
            lines.append(f"- {name}: {story['why']}. Next: {_plain(story['next'])}.")
    if d["team"]:
        lines += ["", "## Team"]
        lines += [f"- {w['who']}: {w['open']} open, {w['overdue']} overdue" for w in d["team"]]
    lines += ["", "Estimates come from an experimental model. Recorded figures come from check-ins, "
              "plays and payments in GymPulse AI."]
    return "\n".join(lines)


def weekly_report_pdf(supabase, gym_id, roster, actions, business_name, days=7):
    import gympulse_reports as rp
    d = weekly_report_data(supabase, gym_id, roster, actions, days)
    rev, res = d["rev"], d["res"]
    rate = "n/a" if rev["renewal_rate"] is None else f"{rev['renewal_rate']:.0%}"
    blocks = [
        ("h", "At a glance"),
        ("kpis", [("Members tracked", f"{d['members']}", "Active members"),
                  ("High risk", f"{d['high']}", "Estimate"),
                  ("Revenue at risk", f"{d['at_risk_rev']:,.0f}", "Per month · estimate"),
                  ("Renewal rate", rate, f"{rev['renewed']} renewed · {rev['lapsed']} lapsed")]),
        ("h", "Retention work this week"),
        ("kpis", [("Plays started", f"{d['started']}", "Recorded"),
                  ("Members contacted", f"{d['contacted']}", "Recorded"),
                  ("Plays closed", f"{d['closed']}", f"Kept {d['kept']} · cancelled {d['lost']}"),
                  ("Overdue now", f"{res['overdue']}", f"{res['due_today']} due today")]),
    ]
    if rev["source"] == "payments":
        blocks += [("h", "Revenue this week"),
                   ("kpis", [("Collected", f"{rev['collected']:,.0f}", f"{rev['renewals_n']} renewal payment(s)"),
                             ("Credited to plays", f"{rev['retained_by_plays']:,.0f}",
                              f"{rev['credited_n']} renewal(s)"),
                             ("Recovered", f"{rev['recovered']:,.0f}", f"{rev['recovered_n']} lapsed member(s)")])]
        if rev["by_play"]:
            blocks.append(("table", ["Play", "Revenue credited"],
                           [[k, f"{v:,.0f}"] for k, v in sorted(rev["by_play"].items(), key=lambda kv: -kv[1])],
                           [3, 1]))
    blocks.append(("h", "Who needs you next week"))
    blocks.append(("table", ["Member", "Why", "Next step"],
                   [[n, s["why"], _plain(s["next"])] for n, s in d["need"]], [1.3, 3, 1.7]))
    if d["team"]:
        blocks.append(("h", "Team workload"))
        blocks.append(("table", ["Staff", "Open plays", "Overdue", "Follow-ups due"],
                       [[w["who"], w["open"], w["overdue"], w["follow_up_due"]] for w in d["team"]]))
    blocks.append(("note", "Recorded figures come from check-ins, retention plays and payments in GymPulse AI. "
                           "Risk levels and revenue at risk are estimates from an experimental model. Revenue "
                           "credited to a play shows the play was involved in the renewal, not proof the member "
                           "would otherwise have left."))
    return rp.build_pdf("Weekly retention report",
                        f"{d['start']:%d %b} to {d['end']:%d %b %Y}", blocks, business_name)


def render_report_section(supabase, gym_id, roster, actions, business_name):
    import gympulse_reports as rp
    st.markdown('<div class="section-label">WEEKLY REPORT</div>', unsafe_allow_html=True)
    report = weekly_report(supabase, gym_id, roster, actions, business_name)
    c1, c2 = st.columns(2)
    with c1:
        try:
            pdf = weekly_report_pdf(supabase, gym_id, roster, actions, business_name)
            rp.download_link("Download weekly report (PDF)", pdf,
                             f"GymPulse-weekly-report-{gw.today_local():%Y-%m-%d}.pdf", rp.PDF,
                             "weekly_pdf", primary=True)
        except Exception as error:
            st.error(f"Could not build the PDF: {error}")
    owner_email = (st.session_state.get("auth_user") or {}).get("email", "")
    try:
        import gympulse_followups as fu
        can_email = fu.email_ready() and bool(owner_email)
    except Exception:
        can_email = False
    if can_email and c2.button(f"Email it to {owner_email}", key="rep_email", use_container_width=True):
        try:
            fu.send_email(owner_email, f"{business_name} · Weekly retention report", report)
            st.success("Report sent.")
        except Exception as error:
            st.error(f"Could not send: {error}")
    elif not can_email:
        c2.caption("Connect email sending (RESEND_API_KEY and EMAIL_FROM on Render) to email "
                   "this report to yourself.")
    with st.expander("Preview the report"):
        st.markdown(report)
