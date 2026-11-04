"""Email every gym its monthly retention report (run on the 1st of each month).

Render: New -> Cron Job, same repository, schedule `0 7 1 * *` (07:00 UTC = 08:00 Lagos),
command `python scripts/send_monthly_reports.py`, and the environment variables
SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY and RESEND_API_KEY (optionally REPORTS_FROM).

  python scripts/send_monthly_reports.py              # last month, every gym not yet emailed
  python scripts/send_monthly_reports.py --month 2026-10
  python scripts/send_monthly_reports.py --dry-run    # list what would be sent
"""
import argparse
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging                         # noqa: E402
logging.getLogger("streamlit").setLevel(logging.ERROR)
import gympulse_monitoring as gmon   # noqa: E402
gmon.init("scheduled job")   # hide "missing ScriptRunContext" noise

import gympulse_admin as gadm          # noqa: E402
import gympulse_workspaces as gw       # noqa: E402


def month_range(text=None):
    if text:
        y, m = (int(x) for x in text.split("-"))
        start = date(y, m, 1)
    else:
        first_this = gw.today_local().replace(day=1)
        start = (first_this - timedelta(days=1)).replace(day=1)
    nxt = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return start, nxt - timedelta(days=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", help="YYYY-MM (default: last month)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    sc = gadm.service_client()
    if sc is None:
        print("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
        return 1
    start, end = month_range(args.month)
    print(f"Monthly reports for {start:%B %Y}")
    if args.dry_run:
        done = gadm.sent_log(sc, f"{start:%Y-%m}") or {}
        for e in gadm.all_gyms(sc):
            state = "already sent" if (e["gym"]["id"], "email") in done else "would send"
            print(f"  {state:13} {e['name']} -> {e['email'] or 'NO EMAIL'}")
        return 0
    sent, skipped, failed = gadm.send_all(sc, start, end, sent_by="cron")
    print(f"Done: {sent} sent, {skipped} already sent, {failed} failed.")
    return 1 if failed and not sent else 0


if __name__ == "__main__":
    sys.exit(main())
