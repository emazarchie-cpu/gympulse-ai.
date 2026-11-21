"""GymPulse AI · the Monday WhatsApp to gym owners: the members to call this week.

Every Monday morning (scripts/send_owner_weekly.py, .github/workflows/owner-weekly.yml) each owner who switched
it on in Settings -> Preferences gets one WhatsApp with up to 3 members to call, picked the same way as
"Today's priorities" on the Dashboard. It uses the gp_owner_weekly template, so it only goes out once Meta has
approved that template (Admin -> WhatsApp -> Submit). One message per gym per week (platform_reports).
"""
from datetime import timedelta

import gympulse_workspaces as gw

TEMPLATE = "gp_owner_weekly"
TOP_N = 3


def owner_cfg(profile):
    c = dict(dict((profile or {}).get("settings") or {}).get("owner_weekly") or {})
    return {"on": bool(c.get("on")), "phone": gw._text(c.get("phone")).strip()}


def week_period(today=None):
    y, w, _ = (today or gw.today_local()).isocalendar()
    return f"{y}-W{w:02d}"


def top_members(supabase, gym_id, n=TOP_N):
    """The members to call this week, most urgent first, the same order as the Dashboard's priorities."""
    import gympulse_model as gm
    roster, _ = gw.load_roster(supabase, gym_id, gm.assess_members, with_photos=False)
    if roster is None or roster.empty:
        return []
    actions = gw.load_actions(supabase, gym_id)
    need = gw.members_to_contact(roster, actions)
    if need is None or need.empty:
        return []
    ranked = need.assign(_urgent=(need["risk_category"] == "High") & (need["renewal_due_days"] <= 30),
                         _value=need["cancellation_probability"] * need["monthly_fee"]
                         ).sort_values(["_urgent", "_value"], ascending=False)
    return [r for _, r in ranked.head(n).iterrows()]


def member_line(r):
    first = (gw._text(r.get("full_name")).split() or ["Member"])[0]
    why = gw._text(r.get("drivers")).split(", ")[0]
    return f"{first} ({why})" if why and why != "no major warning signs" else first


def params(owner_name, gym_name, rows):
    first = (gw._text(owner_name).split() or ["there"])[0]
    return [first, gw._text(gym_name, "your gym"), "; ".join(member_line(r) for r in rows)]


def send_all(sc, dry_run=False, log=print, today=None):
    """Send this week's message to every owner who switched it on. Returns (sent, skipped, failed)."""
    import gympulse_admin as gadm
    import gympulse_billing as gbill
    import gympulse_whatsapp as gwa
    if not gwa.ready():
        log("WhatsApp isn't set up (WHATSAPP_TOKEN, WHATSAPP_PHONE_ID).")
        return 0, 0, 0
    if not dry_run:
        statuses = gwa.template_statuses()
        if statuses is not None and statuses.get(TEMPLATE) != "APPROVED":
            log(f"Template {TEMPLATE} is {statuses.get(TEMPLATE) or 'not submitted'}: submit it in Admin -> WhatsApp.")
            return 0, 0, 0
    period = week_period(today)
    done = gadm.sent_log(sc, period) or {}
    locked = gbill.locked_gyms(sc)
    sent = skipped = failed = 0
    for entry in gadm.all_gyms(sc, fresh=True):
        gid = entry["gym"]["id"]
        cfg = owner_cfg(entry["profile"])
        digits = gw.whatsapp_digits(cfg["phone"])
        if not cfg["on"] or len(digits) < 10 or gid in locked or gadm._is_banned(entry):
            continue
        if (gid, "whatsapp") in done:
            skipped += 1
            continue
        try:
            with gadm.as_gym(entry):
                rows = top_members(sc, gid)
            if not rows:
                log(f"{entry['name']}: nobody to call this week")
                skipped += 1
                continue
            p = params(entry["owner"], entry["name"], rows)
            log(f"{entry['name']}: {p[2]}" + (" (dry run)" if dry_run else ""))
            if not dry_run:
                gwa.send_template(digits, TEMPLATE, p)
                gadm.log_sent(sc, gid, period, "whatsapp", "weekly")
            sent += 1
        except Exception as error:
            log(f"{entry['name']}: failed: {str(error)[:200]}")
            failed += 1
    return sent, skipped, failed
