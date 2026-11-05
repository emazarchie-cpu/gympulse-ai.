"""Send every gym's automatic messages for today (renewal reminders, we missed you, reward ready).

Runs every morning from .github/workflows/auto-messages.yml. Only gyms that switched a
message on in Grow -> Automatic messages are affected; suspended owners are skipped.

  python scripts/send_auto_messages.py            # send
  python scripts/send_auto_messages.py --dry-run  # list what would be sent
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
import gympulse_loyalty as gl        # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    sc = gadm.service_client()
    if sc is None:
        print("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
        return 1
    import gympulse_billing as gbill
    levels = gbill.gym_levels(sc)
    total = [0, 0, 0]
    for entry in gadm.all_gyms(sc, fresh=True):
        if levels.get(entry["gym"]["id"], 3) < 2:      # Starter plan: renewal reminders only
            settings = dict(entry["profile"].get("settings") or {})
            auto_raw = dict(settings.get("auto_messages") or {})
            auto_raw["missed"] = {**dict(auto_raw.get("missed") or {}), "on": False}
            auto_raw["reward"] = {**dict(auto_raw.get("reward") or {}), "on": False}
            entry = {**entry, "profile": {**entry["profile"], "settings": {**settings, "auto_messages": auto_raw}}}
        auto = gl.auto_cfg(entry["profile"])
        if not (auto["renewal"]["on"] or auto["missed"]["on"] or auto["reward"]["on"]):
            continue
        if gadm._is_banned(entry):
            print(f"{entry['name']}: suspended, skipped")
            continue
        print(entry["name"])
        try:
            with gadm.as_gym(entry):
                s, k, f = gl.send_due(sc, entry["gym"]["id"], entry["profile"], dry_run=args.dry_run)
        except Exception as error:
            print(f"  failed: {error}")
            total[2] += 1
            continue
        print(f"  {s} {'would send' if args.dry_run else 'sent'}, {k} skipped, {f} failed")
        total = [total[0] + s, total[1] + k, total[2] + f]
    print(f"Done: {total[0]} {'would send' if args.dry_run else 'sent'}, {total[1]} skipped, {total[2]} failed.")
    print("Trial and renewal reminders")
    n = gbill.trial_reminders(sc, gadm.all_gyms(sc, fresh=True), dry_run=args.dry_run)
    print(f"  {n} {'would send' if args.dry_run else 'sent'}")
    if not args.dry_run:
        print("Paystack payments")
        try:
            print(f"  {gbill.reconcile_paystack(sc)} switched on")
        except Exception as error:
            print(f"  failed: {error}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
