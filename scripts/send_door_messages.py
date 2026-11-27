"""Send the renewal message to members stopped at the door because their membership expired.

Runs every 10 minutes from .github/workflows/door-messages.yml, so the message arrives while the member is
still at the door. Only gyms with door access, a refusal today, and the setting on (Settings -> Check-in
devices -> Door access). Each member gets it once a day at most, through the same channels as the gym's
automatic messages, with their own pay link.

  python scripts/send_door_messages.py            # send
  python scripts/send_door_messages.py --dry-run  # list what would be sent
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.getLogger("streamlit").setLevel(logging.ERROR)
import gympulse_monitoring as gmon   # noqa: E402
gmon.init("scheduled job")

import pandas as pd                  # noqa: E402

import gympulse_admin as gadm        # noqa: E402
import gympulse_loyalty as gl        # noqa: E402
import gympulse_workspaces as gw     # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    sc = gadm.service_client()
    if sc is None:
        print("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
        return 1
    start = pd.Timestamp(gw.today_local()).tz_localize(gw.APP_TZ).tz_convert("UTC").isoformat()
    try:
        rows = (sc.table("door_events").select("gym_id, reason").eq("allowed", False).gte("at", start)
                .limit(5000).execute().data or [])
    except Exception as error:
        print(f"door_events not available ({error}): run sql/phase45_door_access.sql")
        return 0
    gyms = {r["gym_id"] for r in rows if str(r.get("reason") or "").startswith("Membership expired")}
    if not gyms:
        print("No one stopped for an expired plan today.")
        return 0
    import gympulse_billing as gbill
    locked = gbill.locked_gyms(sc)
    total = [0, 0, 0]
    for entry in gadm.all_gyms(sc, fresh=True):
        gid = entry["gym"]["id"]
        if gid not in gyms or gid in locked or gadm._is_banned(entry):
            continue
        if (entry.get("email") or "").lower() == gadm.DEMO_EMAIL:      # sample members: never message them
            continue
        print(entry["name"])
        try:
            with gadm.as_gym(entry):
                s, k, f = gl.send_due(sc, gid, entry["profile"], dry_run=args.dry_run, door_only=True)
        except Exception as error:
            print(f"  failed: {error}")
            gmon.capture(error, "door messages")
            continue
        print(f"  {s} {'would send' if args.dry_run else 'sent'}, {k} skipped, {f} failed")
        total = [total[0] + s, total[1] + k, total[2] + f]
    print(f"Done: {total[0]} {'would send' if args.dry_run else 'sent'}, {total[1]} skipped, {total[2]} failed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
