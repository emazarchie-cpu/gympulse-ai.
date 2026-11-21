"""Monday WhatsApp to gym owners: the members to call this week (see gympulse_weekly.py).

Runs every Monday from .github/workflows/owner-weekly.yml. Only owners who switched it on in
Settings -> Preferences get it, and only once the gp_owner_weekly template is approved by Meta.

  python scripts/send_owner_weekly.py            # send
  python scripts/send_owner_weekly.py --dry-run  # list what would be sent
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.getLogger("streamlit").setLevel(logging.ERROR)
import gympulse_monitoring as gmon   # noqa: E402
gmon.init("scheduled job")

import gympulse_admin as gadm        # noqa: E402
import gympulse_weekly as gwk        # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    sc = gadm.service_client()
    if sc is None:
        print("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
        return 1
    s, k, f = gwk.send_all(sc, dry_run=args.dry_run)
    print(f"Done: {s} {'would send' if args.dry_run else 'sent'}, {k} skipped, {f} failed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
