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
  * first-week check-in, 7 days after joining
  * new member check-in, about two weeks after joining (warmer if they've barely come)
  * milestones: 25/50/100+ visits, 12 strong weeks in a row, joining anniversaries
  * loyalty level up (Bronze → Silver → Gold), when levels are on
  * happiness check, a one-tap question every 3 months (or monthly)
  * monthly progress note, early each month, to members who trained 4+ times last month
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

SQL_HINT = ("This needs a one-time setup: open Supabase, go to SQL Editor, paste in the file "
            "sql/phase9_loyalty.sql and press Run.")

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
    "levels_on": False,
    "levels": [{"name": "Bronze", "points": 0, "perk": ""},
               {"name": "Silver", "points": 1000, "perk": "10% off drinks and merch"},
               {"name": "Gold", "points": 3000, "perk": "A free personal training session every quarter"}],
}
AUTO_DEFAULTS = {
    "renewal": {"on": False, "days": 3},
    "missed": {"on": False, "days": 10, "pause": True},
    "reward": {"on": False},
    "week1": {"on": False},
    "welcome": {"on": False},
    "progress": {"on": False},
    "milestone": {"on": False},
    "level": {"on": False},
    "pulse": {"on": False, "freq": "quarter"},
    "daily_cap": 80,
}


AUTO_KINDS = ("renewal", "missed", "week1", "welcome", "milestone", "level", "reward", "progress", "pulse")


def _settings(profile=None):
    p = profile or st.session_state.get("user_profile") or {}
    return dict(p.get("settings") or {})


def loyalty_cfg(profile=None):
    cfg = {**LOYALTY_DEFAULTS, **dict(_settings(profile).get("loyalty") or {})}
    cfg["rewards"] = sorted([r for r in cfg.get("rewards") or [] if r.get("name") and int(r.get("points") or 0) > 0],
                            key=lambda r: int(r["points"]))
    return cfg


def level_for(earned, cfg):
    """(level, next level or None) from points earned (gifts claimed don't lower a level)."""
    levels = sorted([l for l in cfg.get("levels") or [] if gw._text(l.get("name"))], key=lambda l: int(l.get("points") or 0))
    if not (cfg.get("levels_on") and levels):
        return None, None
    cur = levels[0]
    for l in levels:
        if earned >= int(l.get("points") or 0):
            cur = l
    nxt = next((l for l in levels if int(l.get("points") or 0) > earned), None)
    return cur, nxt


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
                    out.append(("missed", md, ref) + missed_letter(md, lv, away, gg.member_story(md, ck),
                                                                   auto["missed"].get("pause", True)))
        joined = m.get("joined") if gg._has_date(m.get("joined")) else None
        if auto["week1"]["on"] and joined is not None and 6 <= (today - joined).days <= 9:
            ref = f"week1:{joined.isoformat()}"
            if (m["id"], "week1", ref) not in sent:
                visits = int(ck[ck["member_id"] == m["id"]]["day"].nunique()) if len(ck) else 0
                out.append(("week1", md, ref) + week1_letter(md, visits))
        if auto["welcome"]["on"] and joined is not None and 12 <= (today - joined).days <= 20:
            ref = f"welcome:{joined.isoformat()}"
            if (m["id"], "welcome", ref) not in sent:
                visits = int(ck[ck["member_id"] == m["id"]]["day"].nunique()) if len(ck) else 0
                out.append(("welcome", md, ref) + welcome_letter(md, visits))
        if auto["progress"]["on"] and today.day <= 7 and (end is None or end >= today) and len(ck):
            first_this = today.replace(day=1)
            last_month_start = (first_this - timedelta(days=1)).replace(day=1)
            mine = ck[ck["member_id"] == m["id"]]
            days_ = mine.drop_duplicates("day")["day"] if len(mine) else []
            n_last = int(sum(last_month_start <= d.date() < first_this for d in days_)) if len(mine) else 0
            if n_last >= 4:
                prev_start = (last_month_start - timedelta(days=1)).replace(day=1)
                n_prev = int(sum(prev_start <= d.date() < last_month_start for d in days_))
                ref = f"progress:{last_month_start:%Y-%m}"
                if (m["id"], "progress", ref) not in sent:
                    out.append(("progress", md, ref) + progress_letter(md, n_last, n_prev, last_month_start))
    if auto["milestone"]["on"]:
        import gympulse_celebrate as gc
        ck_all = gg._checkins(supabase, gym_id, 1500)
        for _, m in members.iterrows():
            end = m["end"] if gg._has_date(m.get("end")) else None
            if end is not None and end < today:
                continue
            for ref, title, sentence in gc.milestones(m, ck_all, today):
                if (m["id"], "milestone", ref) not in sent:
                    out.append(("milestone", dict(m), ref) + gc.milestone_letter(dict(m), title, sentence))
                    break
    if auto["pulse"]["on"]:
        import gympulse_campaigns as gcamp
        import gympulse_happy as gh
        rnd = gh.round_for(today, auto["pulse"].get("freq", "quarter"))
        ref = f"pulse:{rnd}"
        cands = [m for _, m in members.iterrows()
                 if (not gg._has_date(m.get("end")) or m["end"] >= today)
                 and gg._has_date(m.get("joined")) and (today - m["joined"]).days >= 30
                 and (m["id"], "pulse", ref) not in sent]
        flags = gcamp.member_flags(supabase, gym_id, [m["id"] for m in cands]) if cands else {}
        for m in cands:
            opted, token = flags.get(m["id"], (False, None))
            if token and not opted:
                out.append(("pulse", dict(m), ref) + gh.pulse_letter(dict(m), token, rnd))
    if auto["reward"]["on"] or auto["level"]["on"]:
        cfg, table, _ = compute_points(supabase, gym_id, profile)
        if cfg["enabled"] and len(table):
            by_id = {r["id"]: dict(r) for _, r in members.iterrows()}
            for _, r in table.iterrows():
                lv, _nxt = level_for(int(r["earned"]), cfg)
                if auto["level"]["on"] and lv and int(lv.get("points") or 0) > 0 and r["member_id"] in by_id:
                    ref = f"level:{lv['name']}"
                    if (r["member_id"], "level", ref) not in sent:
                        out.append(("level", by_id[r["member_id"]], ref) + level_letter(r, lv, _nxt))
                if auto["reward"]["on"] and r["ready"] is not None and r["member_id"] in by_id:
                    ref = f"reward:{r['ready']['name']}:{r['claimed']}"
                    if (r["member_id"], "reward", ref) not in sent:
                        subject, body = reward_letter(r, r["ready"], cfg)
                        out.append(("reward", by_id[r["member_id"]], ref, subject, body, None))
    # At most one automatic email per member per day: renewal first, then we missed you,
    # then reward. The others stay due and go out on a later day.
    order = {"renewal": 0, "missed": 1, "week1": 2, "welcome": 3, "milestone": 4, "level": 5, "reward": 6,
             "progress": 7, "pulse": 8}
    picked, seen = [], set(had_today)
    for item in sorted(out, key=lambda x: order[x[0]]):
        if item[1]["id"] not in seen:
            seen.add(item[1]["id"])
            picked.append(item)
    return picked


def missed_letter(m, last_visit, away, story, pause=True):
    import gympulse_grow as gg
    biz, owner = gg._biz()
    first = gg._first(m.get("full_name"))
    prog = gg._progress_line(story, biz)
    body = (f"Hi {first},\n\nWe noticed we haven't seen you at {biz} since {last_visit:%A %d %B}. "
            "Is everything okay?\n\n"
            + (prog + " It would be a shame to lose that momentum.\n\n" if prog else "")
            + "Busy weeks happen to everyone, and even a short session gets you back on track. Reply to this email "
              "with the day you're planning to come in, and we'll have everything ready for you.\n\n"
            + ("If now isn't a good time, whether it's travel, work or anything else, just reply and we can pause "
               "your membership so you don't lose any days.\n\n" if pause else "")
            + f"See you soon,\n{owner}\n{biz}")
    return f"We've missed you at {biz}, {first}", body, None


def week1_letter(m, visits):
    """A week after joining: how was it, and who to talk to."""
    import gympulse_grow as gg
    biz, owner = gg._biz()
    first = gg._first(m.get("full_name"))
    if visits:
        middle = (f"You've already been in {visits} time{'s' if visits != 1 else ''}, nice work. "
                  "How did your first week feel?")
    else:
        middle = ("We haven't seen you in yet, and that's okay: the first visit is always the hardest. "
                  "Is there a day this week that works for you?")
    body = (f"Hi {first},\n\nIt's been a week since you joined {biz}. {middle}\n\n"
            "If anything isn't quite right, or you're not sure where to start, just reply to this email. "
            f"It comes straight to me.\n\n{owner}\n{biz}")
    return f"How was your first week at {biz}, {first}?", body, None


def level_letter(row, level, nxt):
    import gympulse_grow as gg
    biz, owner = gg._biz()
    first = gg._first(row["name"])
    perk = gw._text(level.get("perk"))
    body = (f"Hi {first},\n\nGreat news: you've reached {level['name']} level at {biz}, with "
            f"{int(row['earned']):,} loyalty points from your visits.\n\n"
            + (f"As a {level['name']} member you get: {perk}. Just mention it at the front desk.\n\n" if perk else "")
            + (f"Next up is {nxt['name']} at {int(nxt['points']):,} points. Keep it going!\n\n" if nxt else
               "That's our top level. Thank you for being one of our most committed members!\n\n")
            + f"{owner}\n{biz}")
    return f"{first}, you're now {level['name']} at {biz}!", body, None


def welcome_letter(m, visits):
    """About two weeks after joining. Warmer and more practical if they've barely come in."""
    import gympulse_grow as gg
    biz, owner = gg._biz()
    first = gg._first(m.get("full_name"))
    if visits >= 4:
        subject = f"Two weeks in, {first}: great start"
        middle = (f"You've already been in {visits} times since you joined. That's exactly how habits are built, "
                  "and the first month is the hardest part, so you're doing brilliantly.")
    elif visits >= 1:
        subject = f"How are your first weeks at {biz}, {first}?"
        middle = (f"You've been in {visits} time{'s' if visits != 1 else ''} so far. The first few weeks are the "
                  "trickiest, so a simple plan helps: pick two set days a week and treat them like appointments.")
    else:
        subject = f"Let's get your first session booked, {first}"
        middle = ("We haven't seen you in yet, and that's completely normal: starting is the hardest part. "
                  "Tell us a day and time that suits you, and someone will be ready to show you around.")
    body = (f"Hi {first},\n\nIt's been about two weeks since you joined {biz}. {middle}\n\n"
            "If anything is getting in the way, or you'd like help with a plan, just reply to this email.\n\n"
            f"See you soon,\n{owner}\n{biz}")
    return subject, body, None


def progress_letter(m, n_last, n_prev, month_start):
    """A short, positive note about last month. No numbers they should feel bad about."""
    import gympulse_grow as gg
    biz, owner = gg._biz()
    first = gg._first(m.get("full_name"))
    better = n_prev and n_last > n_prev
    subject = f"{first}, you trained {n_last} times in {month_start:%B}"
    body = (f"Hi {first},\n\nQuick note from {biz}: you trained {n_last} times in {month_start:%B}"
            + (f", up from {n_prev} the month before. That's real progress." if better else ". That's real consistency.")
            + "\n\nResults come from showing up week after week, and you're doing it. Keep it going this month."
            f"\n\n{owner}\n{biz}")
    return subject, body, None


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
    import gympulse_whatsapp as gwa
    wcfg = gwa.wa_settings(profile)
    mode = wcfg["mode"]
    wa_on = mode != "email" and gwa.ready()
    opted = gwa.opt_outs(supabase, gym_id, [d[1]["id"] for d in due]) if wa_on and due else set()
    import gympulse_billing as gbill
    allow = gbill.wa_allowance(supabase, gym_id) if wa_on else {"wa_renew": 0, "wa_promo": 0}
    used = gwa.month_usage(supabase, gym_id) if wa_on else {"utility": 0, "marketing": 0}
    left = {"UTILITY": allow["wa_renew"] - used["utility"], "MARKETING": allow["wa_promo"] - used["marketing"]}
    sent = skipped = failed = 0
    for kind, m, ref, subject, body, buttons in due:
        if sent >= cap:
            skipped += 1
            continue
        has_email = "@" in gw._text(m.get("email"))
        cat = gwa.TEMPLATES.get(gwa.KIND_TEMPLATE.get(kind), {}).get("category", "UTILITY")
        use_wa = bool(wa_on and gwa.to_digits(m.get("phone")) and m["id"] not in opted
                      and kind in gwa.KIND_TEMPLATE and gwa.allowed(kind, wcfg) and left[cat] > 0)
        use_email = has_email and (mode in ("email", "both") or not use_wa)
        if not (use_wa or use_email):
            skipped += 1
            continue
        if dry_run:
            how = " + ".join(x for x, on in (("WhatsApp", use_wa), ("email", use_email)) if on)
            log(f"  would send {kind:8} -> {m.get('full_name')} by {how}")
            left[cat] -= 1 if use_wa else 0
            sent += 1
            continue
        ok_any, why = False, []
        if use_wa:
            ok, msg = gwa.send_member(supabase, gym_id, m, kind, ref, subject, body, buttons, profile)
            ok_any = ok_any or ok
            left[cat] -= 1 if ok else 0
            if not ok:
                why.append(f"WhatsApp: {msg}")
                use_email = has_email            # WhatsApp didn't go: fall back to email
        if use_email:
            ok, msg = gcamp.email_member(supabase, gym_id, m, subject, body, buttons)
            ok_any = ok_any or ok
            if not ok:
                why.append(msg)
        if ok_any:
            sent += 1
            _log(supabase, gym_id, m["id"], kind, ref, "sent")
            log(f"  sent {kind:8} -> {m.get('full_name')}")
        else:
            msg = "; ".join(why)
            if not use_wa and ("unsubscribed" in msg or "no email" in msg):
                skipped += 1
                _log(supabase, gym_id, m["id"], kind, ref, "skipped")
            else:
                failed += 1
                log(f"  failed {kind:8} -> {m.get('full_name')}: {msg}")
                import gympulse_monitoring as gmon
                gmon.capture(RuntimeError(f"automatic {kind} message failed: {msg}"), "automatic messages")
    return sent, skipped, failed


# ================================================================== UI: loyalty
def _redeem(supabase, gym_id, mid, reward):
    try:
        supabase.table("loyalty_redemptions").insert({"gym_id": gym_id, "member_id": mid, "reward": reward["name"],
                                                      "points": int(reward["points"])}).execute()
        gw.bump_data_version()
        st.session_state["grow_flash"] = f"Done. {reward['name']} given, {int(reward['points']):,} points taken off."
    except Exception as error:
        st.session_state["grow_error"] = f"Could not save: {error}. {SQL_HINT}"


def render_loyalty(supabase, gym_id, owner_id):
    import gympulse_grow as gg
    gw.intro("Loyalty points", ":material/loyalty:", "Members get points each time they come to the gym and when they renew on time. "
               "When they have enough points, they get a gift you choose, like a free smoothie or a free session.")
    cfg = loyalty_cfg()
    with st.expander("Points and gifts" + ("" if cfg["enabled"] else " · turn it on here"),
                     expanded=not cfg["enabled"]):
        on = st.toggle("Turn on loyalty points", value=cfg["enabled"], key="loy_on")
        c1, c2, c3, c4 = st.columns(4)
        per_visit = c1.number_input("Points for each visit", 0, 1000, int(cfg["per_visit"]),
                                    help="Coming twice in one day still counts as one visit.")
        week_visits = c2.number_input("Visits in a week for extra points", 1, 7, int(cfg["week_visits"]),
                                      help="For example 3: a member who comes 3 or more times in a week gets extra points.")
        week_bonus = c3.number_input("Extra points for a busy week", 0, 1000, int(cfg["week_bonus"]))
        renewal_bonus = c4.number_input("Points for renewing on time", 0, 5000, int(cfg["renewal_bonus"]),
                                        help="When a member pays before their membership runs out.")
        start = st.date_input("Start counting from", date.fromisoformat(str(cfg.get("start") or gw.today_local())),
                              max_value=gw.today_local(),
                              help="Visits before this date don't earn points. Pick an earlier date to include past visits.")
        st.markdown("**Gifts members can get** (name and how many points it costs)")
        rewards = st.data_editor(pd.DataFrame(cfg["rewards"] or LOYALTY_DEFAULTS["rewards"]), num_rows="dynamic",
                                 use_container_width=True, key="loy_rewards",
                                 column_config={"name": st.column_config.TextColumn("Gift"),
                                                "points": st.column_config.NumberColumn("Points", min_value=1, step=50)})
        st.markdown("**Levels** (members move up as they earn points; claiming gifts never moves them down)")
        lv_on = st.toggle("Turn on levels", value=bool(cfg.get("levels_on")), key="loy_lv_on")
        levels = st.data_editor(pd.DataFrame(cfg.get("levels") or LOYALTY_DEFAULTS["levels"]), num_rows="dynamic",
                                use_container_width=True, key="loy_levels",
                                column_config={"name": st.column_config.TextColumn("Level"),
                                               "points": st.column_config.NumberColumn("Points to reach it", min_value=0,
                                                                                       step=100),
                                               "perk": st.column_config.TextColumn("What they get (optional)")})
        if st.button("Save", type="primary", key="loy_save"):
            lv = sorted([{"name": str(r["name"]).strip(), "points": int(r["points"]) if pd.notna(r.get("points")) else 0,
                          "perk": str(r.get("perk") or "").strip() if pd.notna(r.get("perk")) else ""}
                         for _, r in levels.iterrows() if str(r.get("name") or "").strip()], key=lambda x: x["points"])
            rw = [{"name": str(r["name"]).strip(), "points": int(r["points"])} for _, r in rewards.iterrows()
                  if str(r.get("name") or "").strip() and pd.notna(r.get("points")) and int(r["points"]) > 0]
            gg._save_settings(supabase, owner_id, {"loyalty": {
                "enabled": bool(on), "start": start.isoformat(), "per_visit": int(per_visit),
                "week_visits": int(week_visits), "week_bonus": int(week_bonus),
                "renewal_bonus": int(renewal_bonus), "rewards": rw,
                "levels_on": bool(lv_on), "levels": lv}}, "Loyalty settings saved.")
            st.rerun()
    if not cfg["enabled"]:
        st.info("Turn on loyalty points above to start.")
        return
    cfg, table, reds = compute_points(supabase, gym_id)
    if reds is None:
        st.info(SQL_HINT)
        return
    if table.empty:
        st.info("Add members first.")
        return
    month_start = pd.Timestamp(gw.today_local().replace(day=1))
    gw.kpi_row([("Members with points", str(int((table["earned"] > 0).sum())), "cyan", f"since {cfg['start']}"),
                ("Total points", f"{int(table['earned'].sum()):,}", "lime", "all members together"),
                ("Can get a gift now", str(int(table["ready"].notna().sum())), "amber", "let them know"),
                ("Gifts given", str(len(reds)), "grey",
                 f"{sum(1 for r in reds if pd.Timestamp(str(r['created_at'])[:10]) >= month_start)} this month")])

    if cfg.get("levels_on"):
        counts = {}
        for e in table["earned"]:
            lv, _ = level_for(int(e), cfg)
            if lv:
                counts[lv["name"]] = counts.get(lv["name"], 0) + 1
        st.caption("Members by level: " + " · ".join(f"{k} {v}" for k, v in counts.items()))
    ready = table[table["ready"].notna()]
    if len(ready):
        st.markdown('<div class="section-label">CAN GET A GIFT NOW</div>', unsafe_allow_html=True)
        members = {r["id"]: dict(r) for _, r in gg._members(supabase, gym_id).iterrows()}
        for _, r in ready.iterrows():
            with st.expander(f"{r['name']} · {r['balance']:,} points · {r['ready']['name']}"):
                options = [x for x in cfg["rewards"] if r["balance"] >= int(x["points"])]
                pick = st.selectbox("Gift", range(len(options)), index=len(options) - 1,
                                    format_func=lambda i: f"{options[i]['name']} ({int(options[i]['points']):,} points)",
                                    key=f"loy_pick_{r['member_id']}")
                subject, body = reward_letter(r, options[pick], cfg)
                k = f"loy_msg_{r['member_id']}_{pick}"
                st.session_state.setdefault(k, body)
                st.text_area("Message", key=k, height=200, label_visibility="collapsed")
                m = members.get(r["member_id"], {"id": r["member_id"], "full_name": r["name"]})
                gg.send_row(k, m, f"loy_send_{r['member_id']}", subject, supabase=supabase, gym_id=gym_id)
                st.button("They've collected it", key=f"loy_claim_{r['member_id']}", type="primary",
                          help="Takes the points for this gift off their total.",
                          on_click=_redeem, args=(supabase, gym_id, r["member_id"], options[pick]))

    st.markdown('<div class="section-label">TOP MEMBERS</div>', unsafe_allow_html=True)
    top = table.head(20)
    for i, (_, r) in enumerate(top.iterrows()):
        medal = ["🥇", "🥈", "🥉"][i] if i < 3 and r["balance"] > 0 else f"{i + 1}."
        nxt = r["next"]
        pct = 100 if nxt is None else min(100, round(r["balance"] / max(int(nxt["points"]), 1) * 100))
        hint = "can get any gift" if nxt is None else f"{r['to_next']:,} more points for {nxt['name']}"
        lv, _ = level_for(int(r["earned"]), cfg)
        badge = (f' <span style="font-size:11px;font-weight:700;padding:1px 7px;border-radius:6px;'
                 f'border:1px solid currentColor;opacity:.85">{gw._esc(lv["name"])}</span>') if lv else ""
        c1, c2 = st.columns([6, 1], vertical_alignment="center")
        gw._md(f'<div style="display:flex;align-items:center;gap:12px;margin:6px 0"><div style="width:34px">{medal}</div>'
               f'<div style="flex:1"><b>{gw._esc(r["name"])}</b>{badge} · {r["balance"]:,} points '
               f'<span style="opacity:.7">({r["visits"]} visits, {r["weeks"]} busy weeks, {r["renewals"]} paid on '
               f'time) · {gw._esc(hint)}</span>'
               f'<div class="pbar" style="margin-top:4px"><span style="width:{pct}%;--tone:#B7F34A"></span></div></div></div>', c1)
        c2.button("Profile", key=f"loy_prof_{r['member_id']}", icon=":material/person:", use_container_width=True,
                  on_click=gw.open_profile, args=(r["member_id"], "Grow"))
    if reds:
        with st.expander("Gifts already given"):
            names = dict(zip(table["member_id"], table["name"]))
            gw.table([{"When": str(r["created_at"])[:10], "Member": names.get(r["member_id"], "Member"),
                       "Gift": r["reward"], "Points used": r["points"]} for r in reds])


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
    gw.intro("Automatic messages", ":material/schedule_send:", "Turn these on and GymPulse emails your members for you every morning at 8:30, with your logo. "
               "You don't have to press send. Nobody gets the same email twice.")
    auto = auto_cfg()
    with st.form("auto_form", border=False):
        g1, g2 = st.columns(2)
        with g1.container(border=True):
            st.markdown("##### :material/autorenew: Renewals and win-backs")
            c1, c2 = st.columns([1.3, 1])
            r_on = c1.toggle("Remind them to renew", value=auto["renewal"]["on"])
            r_days = c2.number_input("Days before it ends", 1, 14, int(auto["renewal"]["days"]))
            c3, c4 = st.columns([1.3, 1])
            m_on = c3.toggle("\"We missed you\"", value=auto["missed"]["on"],
                             help="Only for members whose membership is still running.")
            m_days = c4.number_input("Days away", 3, 30, int(auto["missed"]["days"]))
            pause_on = st.checkbox("Offer to pause their membership if now isn't a good time",
                                   value=bool(auto["missed"].get("pause", True)),
                                   help="Many members stop because money or time is tight. A pause keeps them with you.")
        with g2.container(border=True):
            st.markdown("##### :material/person_add: New members")
            wk_on = st.toggle("\"How was your first week?\" (day 7)", value=auto["week1"]["on"])
            w_on = st.toggle("Two-week check-in (day 14)", value=auto["welcome"]["on"],
                             help="Warmer and more practical if they've barely come in. Most members who quit do it "
                                  "in their first 3 months.")
            st.caption("Most members who quit do it in their first 3 months.")
        g3, g4 = st.columns(2)
        with g3.container(border=True):
            st.markdown("##### :material/celebration: Recognition")
            ms_on = st.toggle("Milestones (25, 50, 100+ visits, 12 strong weeks, anniversaries)",
                              value=auto["milestone"]["on"])
            pr_on = st.toggle("Monthly progress note (\"you trained 14 times in October\")",
                              value=auto["progress"]["on"],
                              help="Sent in the first week of the month, only to members who came 4 or more times.")
            rw_on = st.toggle("Gift earned (loyalty must be on)", value=auto["reward"]["on"])
            lv_on = st.toggle("New loyalty level (levels must be on)", value=auto["level"]["on"])
        with g4.container(border=True):
            st.markdown("##### :material/sentiment_satisfied: Feedback")
            hp_on = st.toggle("Happiness check (one tap)", value=auto["pulse"]["on"],
                              help="\"How happy are you with the gym?\" Unhappy answers are emailed to you straight "
                                   "away. See answers in Grow → Happiness.")
            hp_freq = st.radio("How often", ["quarter", "month"], horizontal=True,
                               index=0 if auto["pulse"].get("freq", "quarter") == "quarter" else 1,
                               format_func=lambda v: "Every 3 months" if v == "quarter" else "Every month")
            cap = st.number_input("Most emails in one day", 10, 500, int(auto["daily_cap"]),
                                  help="A limit so you don't send too many at once. The free email plan allows 100 a day.")
        if st.form_submit_button("Save", type="primary"):
            gg._save_settings(supabase, owner_id, {"auto_messages": {
                "renewal": {"on": bool(r_on), "days": int(r_days)},
                "missed": {"on": bool(m_on), "days": int(m_days), "pause": bool(pause_on)},
                "welcome": {"on": bool(w_on)}, "progress": {"on": bool(pr_on)},
                "week1": {"on": bool(wk_on)}, "milestone": {"on": bool(ms_on)}, "level": {"on": bool(lv_on)},
                "pulse": {"on": bool(hp_on), "freq": hp_freq},
                "reward": {"on": bool(rw_on)}, "daily_cap": int(cap)}}, "Automatic messages saved.")
            st.rerun()
    import gympulse_whatsapp as gwa
    gwa.render_gym_setting(supabase, owner_id, gym_id)
    if not any(auto[k]["on"] for k in AUTO_KINDS):
        st.info("Turn on at least one message above. Nothing is sent until you do.")
        return
    due = due_messages(supabase, gym_id)
    if due is None:
        st.info(SQL_HINT)
        return
    label = {"renewal": "Renew reminder", "missed": "We missed you", "reward": "Gift earned",
             "welcome": "New member check-in", "progress": "Monthly progress", "update": "Gym update",
             "week1": "First week", "milestone": "Milestone", "level": "Level up", "pulse": "Happiness check"}
    import gympulse_whatsapp as gwa
    wcfg = gwa.wa_settings()
    wa_on = wcfg["mode"] != "email" and gwa.ready()
    can_wa = lambda d: wa_on and gwa.to_digits(d[1].get("phone")) and gwa.allowed(d[0], wcfg)
    with_email = [d for d in due if "@" in gw._text(d[1].get("email")) or can_wa(d)]
    with_wa = sum(1 for d in due if can_wa(d))
    gw.kpi_row([("To send today", str(len(due)), "cyan", "members who need a message"),
                ("Can be reached", str(len(with_email)), "lime",
                 f"{with_wa} on WhatsApp" if wa_on else "will get it by email"),
                ("No way to reach", str(len(due) - len(with_email)), "amber",
                 "add an email or phone" if wa_on else "send these on WhatsApp yourself"),
                ("Sends itself at", "8:30 am", "grey", "every morning")])
    if due:
        gw.table([{"Member": m.get("full_name"), "Message": label[k], "Email": m.get("email") or "–", "Subject": subj}
                  for k, m, ref, subj, body, b in due], pills={"Message": {v: "cyan" for v in label.values()}}, wide=("Subject",))
        if st.toggle("Show me the email before it goes", key="auto_preview"):
            i = st.selectbox("Whose email?", range(len(due)), key="auto_preview_pick",
                             format_func=lambda j: f"{label[due[j][0]]} · {due[j][1].get('full_name')}")
            k, m, ref, subj, body, b = due[i]
            import gympulse_campaigns as gcamp
            import streamlit.components.v1 as components
            st.markdown(f"**Subject:** {subj}")
            components.html(gcamp.render_message(gcamp.brand(), subj, body, "#", b), height=640, scrolling=True)
        st.button(f"Send these {len(with_email)} now instead of waiting", type="primary", key="auto_now",
                  icon=":material/mail:",
                  disabled=not with_email, on_click=_send_now, args=(supabase, gym_id))
        no_email = [d for d in due if "@" not in gw._text(d[1].get("email"))]
        if no_email:
            with st.expander(f"{len(no_email)} have no email: send on WhatsApp"):
                for k, m, ref, subj, body, b in no_email:
                    st.link_button(f"{label[k]} · {m.get('full_name')}", gg.wa_url(m.get("phone"), body),
                                   use_container_width=True)
    else:
        st.success("No one needs a message today. GymPulse will send them by itself when someone does.")
    _, rows = _sent_refs(supabase, gym_id, 30)
    if rows:
        with st.expander(f"Already sent in the last 30 days ({len(rows)})"):
            names = {r["id"]: r["full_name"] for _, r in gg._members(supabase, gym_id).iterrows()}
            gw.table([{"When": str(r["sent_at"])[:16].replace("T", " "), "Member": names.get(r["member_id"], "Member"),
                       "Message": label.get(r["kind"], r["kind"]),
                       "Status": gw._text(r.get("status"), "sent").capitalize()} for r in rows], pills=("Status",))
