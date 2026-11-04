"""GymPulse AI · Loyalty points and automatic messages.

Loyalty: members earn points from real activity only. They get points for each
day they check in, a bonus for each week they train often enough, and a bonus
for every renewal paid before their plan ended. The gym sets the rewards (e.g.
500 points = a free PT session) and marks them as claimed. Points are worked
out from check-ins and payments, so they can't drift. Claimed rewards are kept
in loyalty_redemptions.

Automatic messages: branded emails that go out by themselves once the gym
switches them on:
  * renewal reminder, N days before a plan ends
  * "we missed you", after N days with no check-in (active members only)
  * reward ready, when a member has enough points for a reward
Each is sent at most once per member per occasion (auto_messages log),
respects unsubscribes, and skips members without an email. They run every
morning from scripts/send_auto_messages.py (GitHub Actions), and the owner can
also send today's batch from the app.
Tables: sql/phase9_loyalty.sql.
"""
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

SQL_HINT = "Run sql/phase9_loyalty.sql in Supabase to switch this on."

LOYALTY_DEFAULTS = {
    "enabled": False,
    "start": None,                 # points count from this date
    "per_visit": 10,               # per day checked in
    "week_visits": 3,              # visits in a week to earn the weekly bonus
    "week_bonus": 20,
    "renewal_bonus": 50,           # renewal paid before the plan ended
    "rewards": [{"name": "Free smoothie", "points": 200},
                {"name": "Free personal training session", "points": 500},
                {"name": "One week free", "points": 1000}],
}
AUTO_DEFAULTS = {
    "renewal": {"on": False, "days": 3},
    "missed": {"on": False, "days": 7},
    "reward": {"on": False},
    "daily_cap": 80,
}


def _settings(profile=None):
    p = profile or st.session_state.get("user_profile") or {}
    return dict(p.get("settings") or {})


def loyalty_cfg(profile=None):
    cfg = {**LOYALTY_DEFAULTS, **dict(_settings(profile).get("loyalty") or {})}
    cfg["rewards"] = sorted([r for r in cfg.get("rewards") or [] if r.get("name") and int(r.get("points") or 0) > 0],
                            key=lambda r: int(r["points"]))
    return cfg


def auto_cfg(profile=None):
    raw = dict(_settings(profile).get("auto_messages") or {})
    out = {}
    for k, v in AUTO_DEFAULTS.items():
        out[k] = {**v, **dict(raw.get(k) or {})} if isinstance(v, dict) else raw.get(k, v)
    return out


# ================================================================== points
def _redemptions(supabase, gym_id):
    try:
        return supabase.table("loyalty_redemptions").select("*").eq("gym_id", gym_id) \
            .order("created_at", desc=True).execute().data or []
    except Exception:
        return None


def points_table(members, checkins, payments, redemptions, cfg, today=None):
    """One row per member: visits, weekly bonuses, on-time renewals, earned, claimed, balance, next reward."""
    today = today or gw.today_local()
    start = pd.Timestamp(cfg.get("start") or today)
    rows = []
    ck = checkins[checkins["at"] >= start] if len(checkins) else checkins
    days = ck.drop_duplicates(["member_id", "day"]) if len(ck) else ck
    visits = days.groupby("member_id").size() if len(days) else pd.Series(dtype=int)
    weeks = pd.Series(dtype=int)
    if len(days):
        w = days.assign(week=days["day"].dt.to_period("W-SUN")).groupby(["member_id", "week"]).size()
        weeks = (w >= int(cfg["week_visits"])).groupby(level=0).sum()
    renewals = pd.Series(dtype=int)
    if payments is not None and len(payments):
        p = payments[(payments["kind"] == "renewal") & payments["member_id"].notna()]
        p = p[pd.to_datetime(p["paid_on"], errors="coerce") >= start]
        renewals = p.groupby("member_id").size()
    claimed = {}
    for r in redemptions or []:
        claimed[r["member_id"]] = claimed.get(r["member_id"], 0) + int(r.get("points") or 0)
    rewards = cfg["rewards"]
    for _, m in members.iterrows():
        mid = m["id"]
        v, wk, rn = int(visits.get(mid, 0)), int(weeks.get(mid, 0)), int(renewals.get(mid, 0))
        earned = v * int(cfg["per_visit"]) + wk * int(cfg["week_bonus"]) + rn * int(cfg["renewal_bonus"])
        bal = earned - claimed.get(mid, 0)
        ready = [r for r in rewards if bal >= int(r["points"])]
        nxt = next((r for r in rewards if bal < int(r["points"])), None)
        rows.append({"member_id": mid, "name": gw._text(m.get("full_name"), "Member"), "email": m.get("email"),
                     "phone": m.get("phone"), "visits": v, "weeks": wk, "renewals": rn, "earned": earned,
                     "claimed": claimed.get(mid, 0), "balance": bal,
                     "ready": ready[-1] if ready else None, "next": nxt,
                     "to_next": (int(nxt["points"]) - bal) if nxt else 0})
    return pd.DataFrame(rows).sort_values("balance", ascending=False) if rows else pd.DataFrame(
        columns=["member_id", "name", "balance"])


def compute_points(supabase, gym_id, profile=None):
    import gympulse_grow as gg
    import gympulse_revenue as gr
    cfg = loyalty_cfg(profile)
    members = gg._members(supabase, gym_id)
    if members.empty:
        return cfg, pd.DataFrame(), []
    span = max((gw.today_local() - date.fromisoformat(str(cfg.get("start") or gw.today_local()))).days + 2, 35)
    ck = gg._checkins(supabase, gym_id, min(span, 400))
    reds = _redemptions(supabase, gym_id)
    return cfg, points_table(members, ck, gr.load_payments(supabase, gym_id), reds or [], cfg), reds


def reward_letter(row, reward, cfg):
    import gympulse_grow as gg
    biz, owner = gg._biz()
    first = gg._first(row["name"])
    return (f"{first}, you've earned a reward at {biz}",
            f"Hi {first},\n\nYou now have {row['balance']:,} loyalty points at {biz}, from {row['visits']} visits"
            + (f" and {row['renewals']} on-time renewal{'s' if row['renewals'] != 1 else ''}" if row["renewals"] else "")
            + f".\n\nThat's enough for: {reward['name']} ({int(reward['points']):,} points).\n\n"
              "Just mention it at the front desk on your next visit and we'll sort it out. Thank you for training "
              f"with us so consistently.\n\nSee you soon,\n{owner}\n{biz}")


# ================================================================== automatic messages
def _sent_refs(supabase, gym_id, since_days=120):
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()
        rows = supabase.table("auto_messages").select("member_id, kind, ref, sent_at").eq("gym_id", gym_id) \
            .gte("sent_at", since).execute().data or []
        return {(r["member_id"], r["kind"], r["ref"]) for r in rows}, rows
    except Exception:
        return None, []


def due_messages(supabase, gym_id, profile=None, today=None):
    """Every automatic message due today: (kind, member dict, ref, subject, body, buttons)."""
    import gympulse_grow as gg
    today = today or gw.today_local()
    auto = auto_cfg(profile)
    sent, sent_rows = _sent_refs(supabase, gym_id)
    if sent is None:
        return None
    today_iso = today.isoformat()
    had_today = {r["member_id"] for r in sent_rows if str(r.get("sent_at") or "")[:10] == today_iso}
    members = gg._members(supabase, gym_id)
    if members.empty:
        return []
    ck = gg._checkins(supabase, gym_id, 120)
    last = ck.groupby("member_id")["day"].max() if len(ck) else pd.Series(dtype="datetime64[ns]")
    pay = dict(_settings(profile).get("collect") or {})
    out = []
    for _, m in members.iterrows():
        md = dict(m)
        end = m["end"] if gg._has_date(m.get("end")) else None
        if auto["renewal"]["on"] and end is not None:
            left = (end - today).days
            if 0 <= left <= int(auto["renewal"]["days"]):
                ref = f"end:{end.isoformat()}"
                if (m["id"], "renewal", ref) not in sent:
                    plan, amount = gg.plan_price(m)
                    subject, body = gg.renewal_email(m["full_name"], amount, plan, end, pay, gg.member_story(md, ck))
                    out.append(("renewal", md, ref, subject, body, gg.renewal_buttons(pay)))
        if auto["missed"]["on"] and end is not None and end >= today and m["id"] in last.index:
            lv = last[m["id"]].date()
            away = (today - lv).days
            if away >= int(auto["missed"]["days"]):
                ref = f"last:{lv.isoformat()}"
                if (m["id"], "missed", ref) not in sent:
                    out.append(("missed", md, ref) + missed_letter(md, lv, away, gg.member_story(md, ck)))
    if auto["reward"]["on"]:
        cfg, table, _ = compute_points(supabase, gym_id, profile)
        if cfg["enabled"] and len(table):
            by_id = {r["id"]: dict(r) for _, r in members.iterrows()}
            for _, r in table.iterrows():
                if r["ready"] is not None and r["member_id"] in by_id:
                    ref = f"reward:{r['ready']['name']}:{r['claimed']}"
                    if (r["member_id"], "reward", ref) not in sent:
                        subject, body = reward_letter(r, r["ready"], cfg)
                        out.append(("reward", by_id[r["member_id"]], ref, subject, body, None))
    # At most one automatic email per member per day: renewal first, then we missed you,
    # then reward. The others stay due and go out on a later day.
    order = {"renewal": 0, "missed": 1, "reward": 2}
    picked, seen = [], set(had_today)
    for item in sorted(out, key=lambda x: order[x[0]]):
        if item[1]["id"] not in seen:
            seen.add(item[1]["id"])
            picked.append(item)
    return picked


def missed_letter(m, last_visit, away, story):
    import gympulse_grow as gg
    biz, owner = gg._biz()
    first = gg._first(m.get("full_name"))
    prog = gg._progress_line(story, biz)
    body = (f"Hi {first},\n\nWe noticed we haven't seen you at {biz} since {last_visit:%A %d %B}. "
            "Is everything okay?\n\n"
            + (prog + " It would be a shame to lose that momentum.\n\n" if prog else "")
            + "Busy weeks happen to everyone, and even a short session gets you back on track. Reply to this email "
              "with the day you're planning to come in, and we'll have everything ready for you.\n\n"
              f"See you soon,\n{owner}\n{biz}")
    return f"We've missed you at {biz}, {first}", body, None


def _log(supabase, gym_id, member_id, kind, ref, status):
    try:
        supabase.table("auto_messages").insert({"gym_id": gym_id, "member_id": member_id, "kind": kind,
                                                "ref": ref, "status": status,
                                                "sent_at": datetime.now(timezone.utc).isoformat()}).execute()
    except Exception:
        pass


def send_due(supabase, gym_id, profile=None, dry_run=False, log=print):
    """Send today's automatic messages for one gym. Returns (sent, skipped, failed)."""
    import gympulse_campaigns as gcamp
    due = due_messages(supabase, gym_id, profile)
    if due is None:
        log("  auto_messages table missing: run sql/phase9_loyalty.sql")
        return 0, 0, 0
    cap = int(auto_cfg(profile).get("daily_cap") or 80)
    sent = skipped = failed = 0
    for kind, m, ref, subject, body, buttons in due:
        if sent >= cap:
            skipped += 1
            continue
        if "@" not in gw._text(m.get("email")):
            skipped += 1
            continue
        if dry_run:
            log(f"  would send {kind:8} -> {m.get('full_name')} <{m.get('email')}>")
            sent += 1
            continue
        ok, msg = gcamp.email_member(supabase, gym_id, m, subject, body, buttons)
        if ok:
            sent += 1
            _log(supabase, gym_id, m["id"], kind, ref, "sent")
            log(f"  sent {kind:8} -> {m.get('full_name')}")
        else:
            if "unsubscribed" in msg or "no email" in msg:
                skipped += 1
                _log(supabase, gym_id, m["id"], kind, ref, "skipped")
            else:
                failed += 1
                log(f"  failed {kind:8} -> {m.get('full_name')}: {msg}")
    return sent, skipped, failed


# ================================================================== UI: loyalty
def _redeem(supabase, gym_id, mid, reward):
    try:
        supabase.table("loyalty_redemptions").insert({"gym_id": gym_id, "member_id": mid, "reward": reward["name"],
                                                      "points": int(reward["points"])}).execute()
        gw.bump_data_version()
        st.session_state["grow_flash"] = f"{reward['name']} claimed: {int(reward['points']):,} points used."
    except Exception as error:
        st.session_state["grow_error"] = f"Could not save: {error}. {SQL_HINT}"


def render_loyalty(supabase, gym_id, owner_id):
    import gympulse_grow as gg
    st.caption("Members earn points for every day they train, every strong week, and every on-time renewal. "
               "You choose the rewards. Points come from real check-ins and payments only.")
    cfg = loyalty_cfg()
    with st.expander("Points and rewards" + ("" if cfg["enabled"] else " · switch loyalty on"),
                     expanded=not cfg["enabled"]):
        on = st.toggle("Loyalty points on", value=cfg["enabled"], key="loy_on")
        c1, c2, c3, c4 = st.columns(4)
        per_visit = c1.number_input("Points per visit", 0, 1000, int(cfg["per_visit"]), help="One visit per day counts.")
        week_visits = c2.number_input("Visits for a strong week", 1, 7, int(cfg["week_visits"]))
        week_bonus = c3.number_input("Strong-week bonus", 0, 1000, int(cfg["week_bonus"]))
        renewal_bonus = c4.number_input("On-time renewal bonus", 0, 5000, int(cfg["renewal_bonus"]),
                                        help="Renewal paid before the plan ended.")
        start = st.date_input("Count points from", date.fromisoformat(str(cfg.get("start") or gw.today_local())),
                              max_value=gw.today_local(), help="Earlier visits and renewals don't count.")
        st.markdown("**Rewards**")
        rewards = st.data_editor(pd.DataFrame(cfg["rewards"] or LOYALTY_DEFAULTS["rewards"]), num_rows="dynamic",
                                 use_container_width=True, key="loy_rewards",
                                 column_config={"name": st.column_config.TextColumn("Reward"),
                                                "points": st.column_config.NumberColumn("Points", min_value=1, step=50)})
        if st.button("Save loyalty settings", type="primary", key="loy_save"):
            rw = [{"name": str(r["name"]).strip(), "points": int(r["points"])} for _, r in rewards.iterrows()
                  if str(r.get("name") or "").strip() and pd.notna(r.get("points")) and int(r["points"]) > 0]
            gg._save_settings(supabase, owner_id, {"loyalty": {
                "enabled": bool(on), "start": start.isoformat(), "per_visit": int(per_visit),
                "week_visits": int(week_visits), "week_bonus": int(week_bonus),
                "renewal_bonus": int(renewal_bonus), "rewards": rw}}, "Loyalty settings saved.")
            st.rerun()
    if not cfg["enabled"]:
        st.info("Switch loyalty points on above to start counting.")
        return
    cfg, table, reds = compute_points(supabase, gym_id)
    if reds is None:
        st.info(SQL_HINT)
        return
    if table.empty:
        st.info("Add members first.")
        return
    month_start = pd.Timestamp(gw.today_local().replace(day=1))
    gw.kpi_row([("Members earning", str(int((table["earned"] > 0).sum())), "cyan", f"since {cfg['start']}"),
                ("Points earned", f"{int(table['earned'].sum()):,}", "lime", "all members"),
                ("Ready for a reward", str(int(table["ready"].notna().sum())), "amber", "tell them"),
                ("Rewards claimed", str(len(reds)), "grey",
                 f"{sum(1 for r in reds if pd.Timestamp(str(r['created_at'])[:10]) >= month_start)} this month")])

    ready = table[table["ready"].notna()]
    if len(ready):
        st.markdown('<div class="section-label">READY FOR A REWARD</div>', unsafe_allow_html=True)
        members = {r["id"]: dict(r) for _, r in gg._members(supabase, gym_id).iterrows()}
        for _, r in ready.iterrows():
            with st.expander(f"{r['name']} · {r['balance']:,} points · {r['ready']['name']}"):
                options = [x for x in cfg["rewards"] if r["balance"] >= int(x["points"])]
                pick = st.selectbox("Reward", range(len(options)), index=len(options) - 1,
                                    format_func=lambda i: f"{options[i]['name']} ({int(options[i]['points']):,} points)",
                                    key=f"loy_pick_{r['member_id']}")
                subject, body = reward_letter(r, options[pick], cfg)
                k = f"loy_msg_{r['member_id']}_{pick}"
                st.session_state.setdefault(k, body)
                st.text_area("Message", key=k, height=200, label_visibility="collapsed")
                m = members.get(r["member_id"], {"id": r["member_id"], "full_name": r["name"]})
                gg.send_row(k, m, f"loy_send_{r['member_id']}", subject, supabase=supabase, gym_id=gym_id)
                st.button("Mark reward as claimed", key=f"loy_claim_{r['member_id']}", type="primary",
                          on_click=_redeem, args=(supabase, gym_id, r["member_id"], options[pick]))

    st.markdown('<div class="section-label">LEADERBOARD</div>', unsafe_allow_html=True)
    top = table.head(20)
    for i, (_, r) in enumerate(top.iterrows()):
        medal = ["🥇", "🥈", "🥉"][i] if i < 3 and r["balance"] > 0 else f"{i + 1}."
        nxt = r["next"]
        pct = 100 if nxt is None else min(100, round(r["balance"] / max(int(nxt["points"]), 1) * 100))
        hint = "every reward unlocked" if nxt is None else f"{r['to_next']:,} to {nxt['name']}"
        gw._md(f'<div style="display:flex;align-items:center;gap:12px;margin:6px 0"><div style="width:34px">{medal}</div>'
               f'<div style="flex:1"><b>{gw._esc(r["name"])}</b> · {r["balance"]:,} points '
               f'<span style="opacity:.7">({r["visits"]} visits, {r["weeks"]} strong weeks, {r["renewals"]} on-time '
               f'renewals) · {gw._esc(hint)}</span>'
               f'<div class="pbar" style="margin-top:4px"><span style="width:{pct}%;--tone:#B7F34A"></span></div></div></div>')
    if reds:
        with st.expander("Claimed rewards"):
            names = dict(zip(table["member_id"], table["name"]))
            st.dataframe(pd.DataFrame([{"When": str(r["created_at"])[:10], "Member": names.get(r["member_id"], "Member"),
                                        "Reward": r["reward"], "Points": r["points"]} for r in reds]),
                         hide_index=True, use_container_width=True)


# ================================================================== UI: automatic messages
def _send_now(supabase, gym_id):
    lines = []
    s, k, f = send_due(supabase, gym_id, log=lines.append)
    gw.bump_data_version()
    st.session_state["grow_flash" if not f else "grow_error"] = (
        f"Sent {s} automatic message{'s' if s != 1 else ''}" + (f", skipped {k}" if k else "")
        + (f", {f} failed: " + "; ".join(l for l in lines if "failed" in l) if f else "") + ".")


def render_auto(supabase, gym_id, owner_id):
    import gympulse_grow as gg
    st.caption("Branded emails that go out by themselves every morning at 8:30 (Lagos time), each at most once per "
               "member per occasion. Members who unsubscribed or have no email are skipped.")
    auto = auto_cfg()
    with st.form("auto_form"):
        c1, c2 = st.columns([1, 2])
        r_on = c1.toggle("Renewal reminder", value=auto["renewal"]["on"])
        r_days = c2.number_input("Days before the plan ends", 1, 14, int(auto["renewal"]["days"]))
        c3, c4 = st.columns([1, 2])
        m_on = c3.toggle("We missed you", value=auto["missed"]["on"])
        m_days = c4.number_input("Days without a check-in", 3, 30, int(auto["missed"]["days"]),
                                 help="Active members only. Sent once per absence.")
        rw_on = st.toggle("Reward ready (needs loyalty points on)", value=auto["reward"]["on"])
        cap = st.number_input("Most emails per day", 10, 500, int(auto["daily_cap"]),
                              help="Resend's free plan allows 100 emails a day across all gyms.")
        if st.form_submit_button("Save automatic messages", type="primary"):
            gg._save_settings(supabase, owner_id, {"auto_messages": {
                "renewal": {"on": bool(r_on), "days": int(r_days)}, "missed": {"on": bool(m_on), "days": int(m_days)},
                "reward": {"on": bool(rw_on)}, "daily_cap": int(cap)}}, "Automatic messages saved.")
            st.rerun()
    if not (auto["renewal"]["on"] or auto["missed"]["on"] or auto["reward"]["on"]):
        st.info("Switch on at least one message above. Nothing is sent until you do.")
        return
    due = due_messages(supabase, gym_id)
    if due is None:
        st.info(SQL_HINT)
        return
    label = {"renewal": "Renewal reminder", "missed": "We missed you", "reward": "Reward ready"}
    with_email = [d for d in due if "@" in gw._text(d[1].get("email"))]
    gw.kpi_row([("Due today", str(len(due)), "cyan", "across all switched-on messages"),
                ("Will be emailed", str(len(with_email)), "lime", "have an email address"),
                ("No email", str(len(due) - len(with_email)), "amber", "use WhatsApp for these"),
                ("Next run", "8:30 tomorrow" if not due else "8:30 daily", "grey", "automatic")])
    if due:
        st.dataframe(pd.DataFrame([{"Message": label[k], "Member": m.get("full_name"),
                                    "Email": m.get("email") or "–", "Subject": subj}
                                   for k, m, ref, subj, body, b in due]), hide_index=True, use_container_width=True)
        with st.expander("Preview one"):
            k, m, ref, subj, body, b = due[0]
            import gympulse_campaigns as gcamp
            import streamlit.components.v1 as components
            components.html(gcamp.render_message(gcamp.brand(), subj, body, "#", b), height=640, scrolling=True)
        st.button(f"Send today's {len(with_email)} now", type="primary", key="auto_now", icon=":material/mail:",
                  disabled=not with_email, on_click=_send_now, args=(supabase, gym_id))
        no_email = [d for d in due if "@" not in gw._text(d[1].get("email"))]
        if no_email:
            with st.expander(f"{len(no_email)} without an email: send on WhatsApp"):
                for k, m, ref, subj, body, b in no_email:
                    st.link_button(f"{label[k]} · {m.get('full_name')}", gg.wa_url(m.get("phone"), body),
                                   use_container_width=True)
    else:
        st.success("Nothing due today. Messages will go out automatically when they are.")
    _, rows = _sent_refs(supabase, gym_id, 30)
    if rows:
        with st.expander(f"Sent in the last 30 days ({len(rows)})"):
            names = {r["id"]: r["full_name"] for _, r in gg._members(supabase, gym_id).iterrows()}
            st.dataframe(pd.DataFrame([{"When": str(r["sent_at"])[:16].replace("T", " "),
                                        "Message": label.get(r["kind"], r["kind"]),
                                        "Member": names.get(r["member_id"], "Member")} for r in rows]),
                         hide_index=True, use_container_width=True)
