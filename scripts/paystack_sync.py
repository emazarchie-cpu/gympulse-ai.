"""Switch on any GymPulse AI plan paid through Paystack whose payer closed the page before coming back.

Runs every 15 minutes from .github/workflows/paystack-sync.yml (and once a day inside the automatic messages job).
Each payment is applied once, so running it often is safe.

  python scripts/paystack_sync.py
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.getLogger("streamlit").setLevel(logging.ERROR)
import gympulse_monitoring as gmon   # noqa: E402
gmon.init("paystack sync")

import gympulse_admin as gadm        # noqa: E402
import gympulse_billing as gbill     # noqa: E402


def main():
    sc = gadm.service_client()
    if sc is None:
        print("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
        return 1
    if not gbill.paystack_key():
        print("PAYSTACK_SECRET_KEY not set: skipped")
        return 0
    n = gbill.reconcile_paystack(sc, days=3)
    print(f"Paystack payments: {n} switched on")
    return 0


if __name__ == "__main__":
    sys.exit(main())
