"""GymPulse AI: daily follow-up email for owners whose board is piling up.

Finds retention actions that are still 'To do' or 'In progress' and have not
been updated for 24 hours, then sends each gym owner ONE email listing them.
Run it once a day (see .github/workflows/followup_emails.yml).

    python followup_job.py --dry-run     # print what would be sent
    python followup_job.py               # send for real

Environment variables
    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY   (service role key: keep it secret)
    SMTP_HOST, SMTP_PORT (default 465), SMTP_USER, SMTP_PASSWORD
    FROM_EMAIL, FROM_NAME (default "GymPulse AI")
    APP_URL (default https://gympulse-ai.streamlit.app/)
"""
import argparse
import html
import os
import smtplib
import ssl
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

STALE_HOURS = 24
OPEN_STATUSES = ["To do", "In progress"]
MAX_PER_SECTION = 10
FONT = "'Inter',Arial,Helvetica,sans-serif"


# ------------------------------------------------------------------ logic
def parse_ts(value):
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def ago(hours):
    return f"{int(hours)} hours" if hours < 48 else f"{int(hours // 24)} days"


def find_stale(rows, now, hours=STALE_HOURS):
    """Open actions with no update for `hours`, skipping archived members."""
    items = []
    for r in rows:
        member = r.get("members") or {}
        if isinstance(member, list):
            member = member[0] if member else {}
        if member.get("archived") or r.get("status") not in OPEN_STATUSES:
            continue
        ts = parse_ts(r.get("updated_at") or r.get("created_at"))
        if ts is None:
            continue
        waited = (now - ts).total_seconds() / 3600
        if waited < hours:
            continue
        items.append({
            "gym_id": r["gym_id"],
            "member": member.get("full_name") or "A member",
            "action": r.get("action_type") or "Follow-up",
            "status": r["status"],
            "hours": waited,
        })
    return items


def group_by_gym(items):
    grouped = defaultdict(list)
    for it in items:
        grouped[it["gym_id"]].append(it)
    for lst in grouped.values():
        lst.sort(key=lambda i: -i["hours"])          # longest waiting first
    return grouped


def subject_for(items):
    n = len(items)
    return f"Your GymPulse AI board needs attention ({n} waiting)"


def _section_html(title, items):
    if not items:
        return ""
    rows = "".join(
        f'<li style="margin:0 0 6px 0;">{html.escape(i["member"])} '
        f'<span style="color:#000000;">· {html.escape(i["action"])} · '
        f'waiting {ago(i["hours"])}</span></li>'
        for i in items[:MAX_PER_SECTION])
    more = len(items) - MAX_PER_SECTION
    if more > 0:
        rows += f'<li style="margin:0 0 6px 0;">+{more} more on your board</li>'
    return (f'<p style="margin:16px 0 8px 0;font-size:16px;line-height:24px;'
            f'font-weight:800;color:#10182A;">{title} ({len(items)})</p>'
            f'<ul style="margin:0 0 8px 0;padding-left:20px;font-size:15px;'
            f'line-height:24px;color:#000000;">{rows}</ul>')


def build_html(owner_name, business, items, app_url):
    hi = f"Hi {html.escape(owner_name)}," if owner_name else "Hi there,"
    biz = html.escape(business) if business else "your gym"
    in_prog = [i for i in items if i["status"] == "In progress"]
    to_do = [i for i in items if i["status"] == "To do"]
    sections = _section_html("In progress", in_prog) + _section_html("To do", to_do)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light only">
<title>Your GymPulse AI board needs attention</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
</head>
<body style="margin:0;padding:0;background-color:#EEF2F7;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#EEF2F7;">
<tr><td align="center" style="padding:32px 12px;">
  <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;background-color:#FFFFFF;border-radius:16px;overflow:hidden;">
    <tr><td align="center" style="background-color:#10182A;padding:36px 32px 32px 32px;">
      <div style="font-family:{FONT};font-size:32px;line-height:36px;font-weight:800;letter-spacing:-1px;color:#F4F7FB;">GYM<span style="color:#B7F34A;">PULSE</span> AI</div>
      <div style="font-family:{FONT};font-size:13px;line-height:20px;color:#BCC8D8;margin-top:8px;">Smarter insights. Stronger member retention.</div>
    </td></tr>
    <tr><td style="padding:40px 40px 8px 40px;font-family:{FONT};color:#000000;">
      <h1 style="margin:0 0 18px 0;font-size:24px;line-height:32px;font-weight:800;letter-spacing:-0.5px;color:#10182A;">Your board needs attention</h1>
      <p style="margin:0 0 16px 0;font-size:16px;line-height:26px;color:#000000;">{hi}</p>
      <p style="margin:0 0 8px 0;font-size:16px;line-height:26px;color:#000000;">These retention actions at {biz} have not been updated for over 24 hours. Update them or mark them done so no member slips through.</p>
      {sections}
    </td></tr>
    <tr><td align="center" style="padding:24px 40px;">
      <a href="{html.escape(app_url)}" target="_blank" style="display:inline-block;background-color:#B7F34A;color:#10182A;font-family:{FONT};font-size:16px;line-height:20px;font-weight:800;text-decoration:none;padding:15px 36px;border-radius:12px;">Open my Action Centre</a>
    </td></tr>
    <tr><td style="padding:0 40px 8px 40px;font-family:{FONT};color:#000000;">
      <p style="margin:0 0 24px 0;font-size:13px;line-height:20px;color:#000000;">You get this email at most once a day, and only when something has been waiting.</p>
    </td></tr>
    <tr><td style="padding:8px 40px 40px 40px;font-family:{FONT};color:#000000;">
      <p style="margin:0 0 14px 0;font-size:16px;line-height:26px;color:#000000;">Warm regards,</p>
      <p style="margin:0;font-size:16px;line-height:24px;font-weight:800;color:#000000;">Emmanuel Archibong</p>
      <p style="margin:0;font-size:14px;line-height:22px;color:#000000;">Founder and CEO</p>
    </td></tr>
    <tr><td align="center" style="background-color:#10182A;padding:20px 32px;font-family:{FONT};font-size:12px;line-height:18px;color:#BCC8D8;">
      &copy; GymPulse AI &middot; Smarter insights. Stronger member retention.
    </td></tr>
  </table>
</td></tr></table>
</body></html>"""


def build_text(owner_name, business, items, app_url):
    lines = [f"Hi {owner_name}," if owner_name else "Hi there,", "",
             f"These retention actions at {business or 'your gym'} have not been "
             "updated for over 24 hours:", ""]
    for label in ("In progress", "To do"):
        group = [i for i in items if i["status"] == label]
        if group:
            lines.append(f"{label} ({len(group)})")
            lines += [f"  - {i['member']} · {i['action']} · waiting {ago(i['hours'])}"
                      for i in group[:MAX_PER_SECTION]]
            if len(group) > MAX_PER_SECTION:
                lines.append(f"  - +{len(group) - MAX_PER_SECTION} more")
            lines.append("")
    lines += [f"Open your Action Centre: {app_url}", "", "Warm regards,",
              "Emmanuel Archibong", "Founder and CEO"]
    return "\n".join(lines)


# ------------------------------------------------------------ data access
def fetch_open_rows(client, now, hours=STALE_HOURS):
    cutoff = (now - timedelta(hours=hours)).isoformat()
    return (client.table("retention_actions")
            .select("id, gym_id, action_type, status, updated_at, created_at, "
                    "members(full_name, archived)")
            .in_("status", OPEN_STATUSES).lt("updated_at", cutoff)
            .execute().data or [])


def owner_contact(client, owner_id):
    try:
        res = client.auth.admin.get_user_by_id(owner_id)
        user = getattr(res, "user", None) or res
        meta = getattr(user, "user_metadata", None) or {}
        return getattr(user, "email", None), meta.get("full_name")
    except Exception:
        return None, None


def send_email(cfg, to, subject, html_body, text_body):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f'{cfg["from_name"]} <{cfg["from_email"]}>'
    msg["To"] = to
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    port = int(cfg["port"])
    if port == 465:
        with smtplib.SMTP_SSL(cfg["host"], port, context=ssl.create_default_context()) as s:
            s.login(cfg["user"], cfg["password"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(cfg["host"], port) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(cfg["user"], cfg["password"])
            s.send_message(msg)


def load_smtp_config():
    cfg = {
        "host": os.environ.get("SMTP_HOST"), "port": os.environ.get("SMTP_PORT", "465"),
        "user": os.environ.get("SMTP_USER"), "password": os.environ.get("SMTP_PASSWORD"),
        "from_email": os.environ.get("FROM_EMAIL") or os.environ.get("SMTP_USER"),
        "from_name": os.environ.get("FROM_NAME", "GymPulse AI"),
    }
    missing = [k for k in ("host", "user", "password", "from_email") if not cfg[k]]
    return cfg, missing


def run(client, dry_run=True, now=None, cfg=None, sender=send_email,
        app_url="https://gympulse-ai.streamlit.app/"):
    """Returns a list of (gym_id, owner_email, n_items, status) results."""
    now = now or datetime.now(timezone.utc)
    stale = find_stale(fetch_open_rows(client, now), now)
    grouped = group_by_gym(stale)
    if not grouped:
        print("Nothing waiting. No emails sent.")
        return []
    gyms = (client.table("gyms").select("id, owner_id, business_name")
            .in_("id", list(grouped)).execute().data or [])
    results = []
    for gym in gyms:
        items = grouped.get(gym["id"], [])
        email, name = owner_contact(client, gym["owner_id"])
        if not email:
            results.append((gym["id"], None, len(items), "no owner email"))
            continue
        subject = subject_for(items)
        body_html = build_html(name, gym.get("business_name"), items, app_url)
        body_text = build_text(name, gym.get("business_name"), items, app_url)
        if dry_run:
            print(f"[dry run] would email {email}: {subject}\n{body_text}\n")
            results.append((gym["id"], email, len(items), "dry run"))
            continue
        try:
            sender(cfg, email, subject, body_html, body_text)
            results.append((gym["id"], email, len(items), "sent"))
            print(f"Sent to {email} ({len(items)} waiting)")
        except Exception as e:                       # keep going for other owners
            results.append((gym["id"], email, len(items), f"failed: {type(e).__name__}"))
            print(f"FAILED for {email}: {type(e).__name__}")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print, send nothing")
    args = ap.parse_args()

    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        sys.exit("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.")
    cfg, missing = load_smtp_config()
    if missing and not args.dry_run:
        sys.exit("Missing email settings: " + ", ".join(missing))

    from supabase import create_client
    client = create_client(url, key)
    results = run(client, dry_run=args.dry_run, cfg=cfg,
                  app_url=os.environ.get("APP_URL", "https://gympulse-ai.streamlit.app/"))
    if any(r[3].startswith("failed") or r[3] == "no owner email" for r in results):
        sys.exit(1)                                   # makes the GitHub run show as failed


if __name__ == "__main__":
    main()
