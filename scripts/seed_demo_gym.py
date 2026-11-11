"""Create (or reset) the GymPulse AI demo gym, for showing gym owners the app on a phone.

Runs from .github/workflows/seed-demo.yml (Actions -> Demo gym -> Run workflow), with the same
secrets as the other jobs. Every run wipes the demo gym's data and builds it again, so the demo is
always fresh before a pitch. It only ever touches the gym owned by DEMO_EMAIL.

The demo gym has free access (never locked, no member limit) and automatic messages off. Members have
fake 0700 000 phone numbers and no email, so nothing is ever sent to a real person.

What's inside: ~60 members on Monthly / Quarterly / Yearly plans with 90 days of visits (regulars,
members fading away, lapsed, new joiners), payments, follow-ups (open and won), 3 trainers, HMO
members on two HMOs with settings and claims, and a corporate plan.

A new password is set on every run and emailed to the founder; it is never printed.

  python scripts/seed_demo_gym.py            # build or reset the demo
  python scripts/seed_demo_gym.py --dry-run  # say what would happen, change nothing
"""
import argparse
import os
import random
import secrets
import sys
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEMO_EMAIL = os.environ.get("DEMO_EMAIL") or "demo@usegympulseai.com"
DEMO_GYM = "Demo Fitness Lagos"
OWNER = "Demo Owner"
LAGOS = ZoneInfo("Africa/Lagos")
TODAY = datetime.now(LAGOS).date()
SEED = 20261111
PRICES = {"Monthly": 25000, "Quarterly": 65000, "Yearly": 240000}
DAYS = {"Monthly": 30, "Quarterly": 90, "Yearly": 365}
FIRST = ["Adaeze", "Tunde", "Chioma", "Emeka", "Funke", "Ibrahim", "Ngozi", "Segun", "Aisha", "Kelechi",
         "Bisi", "Uche", "Zainab", "Femi", "Amaka", "Yusuf", "Kemi", "Obinna", "Halima", "Dayo",
         "Ifeoma", "Musa", "Toyin", "Chidi", "Fatima", "Bayo", "Nneka", "Sani", "Yemi", "Ebuka"]
LAST = ["Okafor", "Adeyemi", "Bello", "Eze", "Balogun", "Abubakar", "Nwosu", "Ogunleye", "Ibrahim", "Okeke",
        "Afolabi", "Umeh", "Lawal", "Obi", "Adebayo", "Danjuma", "Onyeka", "Salami", "Ekwueme", "Akande"]
GOALS = ["Lose weight", "Build muscle", "Get fitter", "Tone up", "Stay healthy"]


def log(msg):
    print(msg, flush=True)


def at(day, hour, minute=0):
    return datetime.combine(day, time(hour, minute), LAGOS).astimezone(timezone.utc).isoformat()


def try_insert(sc, table, rows, label=None):
    """Insert rows; drop columns an older database doesn't have. Returns the inserted rows."""
    if not rows:
        return []
    rows = [dict(r) for r in rows]
    for _ in range(8):
        try:
            out = []
            for i in range(0, len(rows), 500):
                out += sc.table(table).insert(rows[i:i + 500]).execute().data or []
            return out
        except Exception as error:
            msg = str(error)
            import re
            m = re.search(r"'(\w+)' column|column \"?(\w+)\"? (?:of relation \"\w+\" )?does not exist", msg)
            col = (m.group(1) or m.group(2)) if m else None
            if col and any(col in r for r in rows):
                rows = [{k: v for k, v in r.items() if k != col} for r in rows]
                continue
            log(f"  ! {label or table}: {msg[:200]}")
            return []
    return []


def find_or_create_owner(sc, password, dry):
    users = []
    page = 1
    while True:
        batch = sc.auth.admin.list_users(page=page, per_page=1000)
        batch = getattr(batch, "users", batch) or []
        users += batch
        if len(batch) < 1000:
            break
        page += 1
    user = next((u for u in users if (getattr(u, "email", "") or "").lower() == DEMO_EMAIL.lower()), None)
    import gympulse_legal as glegal
    meta = {"full_name": OWNER, "business_name": DEMO_GYM, "account_type": "gym_owner",
            "legal": glegal.acceptance(DEMO_EMAIL)}
    if dry:
        log(f"would {'reset' if user else 'create'} the login {DEMO_EMAIL}")
        return getattr(user, "id", None)
    if user:
        sc.auth.admin.update_user_by_id(user.id, {"password": password, "email_confirm": True, "user_metadata": meta})
        return user.id
    res = sc.auth.admin.create_user({"email": DEMO_EMAIL, "password": password, "email_confirm": True,
                                     "user_metadata": meta})
    return res.user.id


def ensure_gym(sc, owner_id):
    import gympulse_legal as glegal
    prof = {"id": owner_id, "full_name": OWNER, "business_name": DEMO_GYM,
            "settings": {"legal": glegal.acceptance(DEMO_EMAIL)}}
    try:
        sc.table("profiles").upsert(prof).execute()
    except Exception as error:
        log(f"  ! profile: {str(error)[:160]}")
    rows = sc.table("gyms").select("*").eq("owner_id", owner_id).limit(1).execute().data or []
    if rows:
        gym = rows[0]
    else:
        gym = sc.table("gyms").insert({"owner_id": owner_id, "business_name": DEMO_GYM}).execute().data[0]
    if not str(gym.get("business_name") or "").startswith("Demo"):
        raise SystemExit(f"Refusing to touch gym {gym['id']}: it isn't the demo gym.")
    try:
        sc.table("gyms").update({"business_name": DEMO_GYM, "join_code": gym.get("join_code") or
                                 "demo" + secrets.token_hex(3)}).eq("id", gym["id"]).execute()
    except Exception:
        pass
    try:
        sc.table("gym_subscriptions").upsert({"gym_id": gym["id"], "status": "free", "plan": None,
                                              "note": "Demo gym: free access, never locked",
                                              "updated_at": datetime.now(timezone.utc).isoformat()},
                                             on_conflict="gym_id").execute()
    except Exception as error:
        log(f"  ! subscription: {str(error)[:160]}")
    return gym["id"]


WIPE = ["hmo_claims", "hmo_providers", "payments", "retention_actions", "auto_messages", "checkins",
        "member_activity", "members", "companies", "trainers"]


def wipe(sc, gym_id):
    for t in WIPE:
        try:
            sc.table(t).delete().eq("gym_id", gym_id).execute()
        except Exception as error:
            if "does not exist" not in str(error) and "Could not find" not in str(error):
                log(f"  ! wipe {t}: {str(error)[:120]}")


def visit_days(rng, kind, joined):
    """Visit days over the last 90 days for one kind of member."""
    days = []
    start = max(joined, TODAY - timedelta(days=90))
    d = start
    while d <= TODAY:
        age = (TODAY - d).days
        p = {"regular": 0.45, "steady": 0.3,
             "fading": 0.4 if age > 30 else (0.12 if age > 14 else 0.0),
             "lapsed": 0.35 if age > 45 else 0.0,
             "new": 0.5}[kind]
        if rng.random() < p:
            days.append(d)
        d += timedelta(days=1)
    if kind in ("regular", "steady", "new") and (not days or (TODAY - days[-1]).days > 5):
        days.append(TODAY - timedelta(days=rng.randint(0, 3)))
    return sorted(set(days))


def build(sc, gym_id, rng):
    trainers = try_insert(sc, "trainers", [
        {"gym_id": gym_id, "full_name": "Tunde Bakare", "specialty": "Strength and muscle", "phone": "07000000901",
         "bio": "Ten years coaching strength. Loves a clean deadlift."},
        {"gym_id": gym_id, "full_name": "Amaka Obi", "specialty": "Weight loss", "phone": "07000000902",
         "bio": "Helps busy professionals lose weight and keep it off."},
        {"gym_id": gym_id, "full_name": "Segun Ade", "specialty": "Personal training", "phone": "07000000903",
         "bio": "One-to-one coaching for beginners."}])
    log(f"  trainers: {len(trainers)}")

    kinds = ["regular"] * 26 + ["steady"] * 12 + ["fading"] * 10 + ["lapsed"] * 6 + ["new"] * 6
    rng.shuffle(kinds)
    people, used = [], set()
    for i, kind in enumerate(kinds):
        while True:
            name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            if name not in used:
                used.add(name)
                break
        plan = rng.choices(["Monthly", "Quarterly", "Yearly"], [6, 3, 1])[0]
        joined = TODAY - timedelta(days=rng.randint(10, 25) if kind == "new" else rng.randint(100, 420))
        if kind == "lapsed":
            end = TODAY - timedelta(days=rng.randint(5, 40))
        elif kind == "fading":
            end = TODAY + timedelta(days=rng.randint(2, 12))
        else:
            end = TODAY + timedelta(days=rng.randint(3, DAYS[plan]))
        people.append({"kind": kind, "name": name, "plan": plan, "joined": joined, "end": end, "i": i})

    rows = [{"gym_id": gym_id, "full_name": p["name"], "phone": f"0700000{p['i'] + 1:04d}",
             "age": rng.randint(21, 52), "weight_kg": rng.randint(55, 98), "height_cm": rng.randint(152, 188),
             "fitness_goal": rng.choice(GOALS), "archived": False,
             "created_at": datetime.combine(p["joined"], time(9), LAGOS).astimezone(timezone.utc).isoformat(),
             "membership_end": p["end"].isoformat(),
             "last_renewed_on": (p["end"] - timedelta(days=DAYS[p["plan"]])).isoformat(),
             "last_payment": PRICES[p["plan"]]} for p in people]
    made = try_insert(sc, "members", rows, "members")
    for p, m in zip(people, made):
        p["id"] = m["id"]
    people = [p for p in people if p.get("id")]
    log(f"  members: {len(people)}")

    ck, act = [], []
    for p in people:
        days = visit_days(rng, p["kind"], p["joined"])
        p["days"] = days
        for d in days:
            ck.append({"gym_id": gym_id, "member_id": p["id"], "checked_in_at": at(d, rng.choice([6, 7, 17, 18, 19]),
                                                                                 rng.randint(0, 59)),
                       "source": rng.choice(["front_desk", "scan", "scan"])})
        last30 = sum(1 for d in days if (TODAY - d).days < 30)
        prev30 = sum(1 for d in days if 30 <= (TODAY - d).days < 60)
        act.append({"member_id": p["id"], "gym_id": gym_id, "membership_type": p["plan"],
                    "monthly_fee": round(PRICES[p["plan"]] / (DAYS[p["plan"]] / 30)),
                    "days_since_last_visit": (TODAY - days[-1]).days if days else 60,
                    "visits_last_30_days": last30, "visits_previous_30_days": prev30,
                    "renewal_due_days": min(max((p["end"] - TODAY).days, 0), 730),   # the database allows 0-730
                    "pt_sessions_attended": rng.choice([0, 0, 1, 2, 4]),
                    "updated_at": datetime.now(timezone.utc).isoformat()})
    log(f"  visits: {len(try_insert(sc, 'checkins', ck))}")
    log(f"  activity: {len(try_insert(sc, 'member_activity', act))}")

    pays = []
    for p in people:
        paid = p["end"] - timedelta(days=DAYS[p["plan"]])
        if paid >= TODAY - timedelta(days=100) and paid <= TODAY:
            pays.append({"gym_id": gym_id, "member_id": p["id"], "amount": PRICES[p["plan"]], "paid_on": paid.isoformat(),
                         "covers_until": p["end"].isoformat(), "plan": p["plan"],
                         "kind": "new" if p["kind"] == "new" else "renewal",
                         "method": rng.choice(["Bank transfer", "POS", "Cash", "Bank transfer"])})
    log(f"  payments: {len(try_insert(sc, 'payments', pays))}")

    acts = []
    fading = [p for p in people if p["kind"] == "fading"]
    for j, p in enumerate(fading[:6]):
        acts.append({"gym_id": gym_id, "member_id": p["id"],
                     "action_type": ["Personal call", "Renewal offer", "WhatsApp check-in"][j % 3],
                     "due_date": (TODAY + timedelta(days=j % 2)).isoformat(), "status": "To do",
                     "note": "Hasn't been in for two weeks and renews soon."})
    for p in [p for p in people if p["kind"] == "regular"][:4]:
        done = TODAY - timedelta(days=rng.randint(3, 20))
        acts.append({"gym_id": gym_id, "member_id": p["id"], "action_type": "Personal call",
                     "due_date": done.isoformat(), "status": "Done", "outcome": "Retained",
                     "completed_at": at(done, 11), "contacted_at": at(done, 10), "contact_method": "Call",
                     "note": "Called, came back the next day and renewed."})
    log(f"  follow-ups: {len(try_insert(sc, 'retention_actions', acts))}")

    # HMO members: two HMOs, plans, weekly limits, codes, last month's claim
    hmo = [p for p in people if p["kind"] in ("regular", "steady")][:8]
    for j, p in enumerate(hmo):
        rel = j < 5
        fields = {"hmo_provider": "Reliance HMO" if rel else "Hygeia HMO", "hmo_id": f"{'RL' if rel else 'HY'}-{20391 + j}",
                  "hmo_employer": rng.choice(["Lekki Tech Ltd", "Zenith Logistics", "Ikeja Foods"]),
                  "hmo_valid_until": (TODAY + timedelta(days=rng.choice([20, 60, 120, 200]))).isoformat(),
                  "hmo_plan": "Emerald" if rel else "HyFit Platinum", "hmo_weekly_limit": 2 if rel else 3}
        try:
            sc.table("members").update(fields).eq("id", p["id"]).execute()
        except Exception:
            sc.table("members").update({k: v for k, v in fields.items() if k not in ("hmo_plan", "hmo_weekly_limit")}) \
                .eq("id", p["id"]).execute()
        try:
            sc.table("member_activity").update({"monthly_fee": 0}).eq("member_id", p["id"]).execute()
        except Exception:
            pass
    try_insert(sc, "hmo_providers", [
        {"gym_id": gym_id, "name": "Reliance HMO", "pay_model": "per_visit", "rate": 2500, "weekly_limit": 2,
         "needs_code": False, "claim_days": 30},
        {"gym_id": gym_id, "name": "Hygeia HMO", "pay_model": "per_member", "rate": 8000, "weekly_limit": 3,
         "needs_code": True, "claim_days": 30}])
    m1 = (TODAY.replace(day=1) - timedelta(days=1)).replace(day=1)
    m2 = (m1 - timedelta(days=1)).replace(day=1)
    try_insert(sc, "hmo_claims", [
        {"gym_id": gym_id, "provider": "Reliance HMO", "month": m2.isoformat(), "visits": 31, "members": 5,
         "amount": 77500, "status": "paid", "sent_on": (m2 + timedelta(days=36)).isoformat(),
         "paid_on": (m2 + timedelta(days=80)).isoformat(), "amount_paid": 77500},
        {"gym_id": gym_id, "provider": "Hygeia HMO", "month": m2.isoformat(), "visits": 22, "members": 3,
         "amount": 24000, "status": "sent", "sent_on": (TODAY - timedelta(days=68)).isoformat()}])
    log(f"  HMO members: {len(hmo)}")

    # A corporate plan
    comp = try_insert(sc, "companies", [{"gym_id": gym_id, "name": "Lekki Tech Ltd", "hr_name": "Ngozi Eze",
                                          "hr_email": "hr@example.com", "seats": 10, "monthly_fee": 150000,
                                          "billing_cycle": "quarterly",
                                          "next_renewal": (TODAY + timedelta(days=5)).isoformat()}])
    if comp:
        staff = [p for p in people if p["kind"] in ("steady", "regular") and p not in hmo][:5]
        for p in staff:
            try:
                sc.table("members").update({"company_id": comp[0]["id"]}).eq("id", p["id"]).execute()
            except Exception:
                pass
        log(f"  corporate plan: Lekki Tech Ltd, {len(staff)} staff")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    import logging
    logging.getLogger("streamlit").setLevel(logging.ERROR)
    import gympulse_admin as gadm
    sc = gadm.service_client()
    if sc is None:
        log("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
        return 1
    password = "Demo-" + secrets.token_urlsafe(9)
    owner = find_or_create_owner(sc, password, args.dry_run)
    if args.dry_run:
        log("dry run: nothing changed")
        return 0
    gym_id = ensure_gym(sc, owner)
    log(f"Demo gym {gym_id}: clearing old demo data")
    wipe(sc, gym_id)
    log("Building the demo")
    build(sc, gym_id, random.Random(SEED))
    import gympulse_billing as gbill
    ok = gbill._email_founder(
        "GymPulse AI demo gym is ready",
        f"The demo gym \"{DEMO_GYM}\" has been built (or reset) with fresh sample data.\n\n"
        f"Sign in at https://usegympulseai.com\nEmail: {DEMO_EMAIL}\nPassword: {password}\n\n"
        "Run the 'Demo gym' workflow again any time to reset it (this also sets a new password).\n"
        "Members in the demo have fake phone numbers and no email, so no messages go to real people.")
    log("Password emailed to the founder." if ok else "! Could not email the password: check RESEND_API_KEY.")
    log("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
