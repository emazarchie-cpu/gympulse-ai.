"""GymPulse AI · Bring members in from any software or spreadsheet.

Works with GymMaster, Mindbody, Glofox, Spark, Excel / Google Sheets or any
CSV: each system names its columns differently (and GymMaster lets every gym
pick its own), so the importer:
  1. reads the CSV or Excel file (up to 20,000 members),
  2. guesses which column is which from common headings and lets the owner
     correct any guess,
  3. turns each membership name into a GymPulse plan (editable),
  4. matches existing members by email, phone or name (updates, no duplicates),
  5. shows a one-line summary and a plan breakdown, then imports in batches of
     500: members with their plan type, original plan name, fee, start and end
     date, their visit / check-in history (so attendance continues from the old
     software), and photos (links in the file, or a ZIP of images),
  6. logs each import so it can be undone (sql/phase16_import.sql).
"""
import io
import re
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

NONE = "(not in file)"
FIELDS = [  # key, label, common GymMaster/other headings (lowercase, spaces normalised)
    ("first", "First name", ["first name", "firstname", "first", "given name", "forename"]),
    ("last", "Surname", ["surname", "last name", "lastname", "family name", "last"]),
    ("name", "Full name (if one column)", ["name", "full name", "member name", "member", "fullname", "client name",
                                        "client", "customer name", "names"]),
    ("email", "Email", ["email", "email address", "e-mail", "member email"]),
    ("phone", "Phone", ["mobile", "mobile phone", "mobile number", "cell", "cell phone", "cellphone", "phone",
                        "phone number", "contact number", "home phone", "telephone", "whatsapp", "whatsapp number",
                        "mobile no", "phone no", "tel"]),
    ("dob", "Date of birth", ["date of birth", "dob", "birthday", "birth date", "birthdate"]),
    ("membership", "Membership name", ["membership", "membership type", "membership name", "plan", "membership plan",
                                       "current membership", "membership type name", "pricing option", "package",
                                       "subscription", "membership package", "product"]),
    ("start", "Start date", ["start date", "membership start", "start", "joined", "join date", "member since",
                             "date joined", "membership start date", "activation date", "first visit",
                             "registration date", "date registered"]),
    ("end", "End / expiry date", ["expiry", "expiry date", "end date", "expires", "membership expiry", "membership end",
                                  "expiration date", "end", "membership expiry date", "expire date", "valid until",
                                  "membership end date", "expiration", "renewal date", "due date", "next payment date",
                                  "contract end", "paid until"]),
    ("price", "Price", ["price", "cost", "fee", "amount", "membership price", "price per period", "membership cost",
                        "regular payment", "payment amount"]),
    ("last_visit", "Last visit", ["last visit", "last attendance", "last visited", "last check in", "last checkin",
                                  "last check-in", "last visit date", "last attended", "last check in date",
                                  "last checkin date", "last seen"]),
    ("goal", "Fitness goal", ["goal", "fitness goal", "goals"]),
    ("member_no", "Member ID / number", ["member id", "member number", "member no", "id", "client id",
                                         "membership number", "barcode", "card number", "member code", "customer id"]),
    ("weight", "Weight (kg)", ["weight", "weight kg", "weight (kg)", "body weight"]),
    ("height", "Height (cm)", ["height", "height cm", "height (cm)"]),
    ("visits_30", "Visits in the last 30 days", ["visits last 30 days", "visits in last 30 days", "visits this month",
                                                 "attendance last 30 days", "visits (30 days)", "visits 30 days",
                                                 "check ins last 30 days", "recent visits"]),
    ("trainer", "Personal trainer", ["personal trainer", "trainer", "pt trainer", "assigned trainer",
                                     "trainer name", "personal trainer name", "coach", "assigned coach", "pt coach"]),
    ("has_pt", "Personal training (yes / no)", ["personal training", "pt", "has pt", "pt client", "pt member",
                                                 "pt package", "personal training client", "pt sessions",
                                                 "personal training sessions"]),
    ("photo", "Photo link", ["photo", "photo url", "picture", "image", "avatar", "profile picture", "photo link",
                             "image url", "picture url", "profile photo"]),
]
SOURCES = {
    "GymMaster": "In GymMaster open **Reports**, run a member list or memberships report, use **Add Column** to "
                 "include First Name, Surname, Email, Mobile, Membership, Start Date, Expiry Date, Price and Last "
                 "Visit, then **Export to CSV**. Leaving GymMaster? Its cancellation step also offers a full data export.",
    "Mindbody": "In Mindbody open **Reports → Client lists** (or Memberships), include name, email, phone, "
                "membership and expiration date, then **Export → Excel/CSV**.",
    "Glofox": "In Glofox open **Members**, filter to active members, and use **Export** (CSV). Include membership "
              "name and expiry date.",
    "Spark / other gym software": "Look for **Reports** or **Members → Export** and download a CSV with name, email, "
                                  "phone, membership and end date. Most systems have this.",
    "Excel or Google Sheets": "Use one row per member with columns such as Name, Phone, Email, Plan, Start date, "
                              "End date and Amount. In Google Sheets: **File → Download → CSV**.",
    "Paper register or WhatsApp list": "Type the list into Excel or Google Sheets (Name, Phone, Plan, End date is "
                                       "enough), or share your **member sign-up link** so members fill in their own "
                                       "details (Members → Member sign-up link).",
}
MAX_ROWS = 20000
BATCH = 500
PLAN_WORDS = [  # (pattern, GymPulse plan), checked in order
    (r"\b(daily|day pass|1 ?day|one day|casual|drop.?in)\b", "Daily"),
    (r"\b(2|two) ?weeks?\b|fortnight", "2 weeks"),
    (r"\bweek(ly)?\b|7 ?days?", "Weekly"),
    (r"\b(12|twelve) ?months?\b|year|annual", "Yearly"),
    (r"\b(6|six) ?months?\b|half.?year|bi.?annual", "6 months"),
    (r"\b(3|three) ?months?\b|quarter", "Quarterly"),
    (r"\b(2|two) ?months?\b", "2 months"),
    (r"\bmonth(ly)?\b|30 ?days?|1 ?month", "Monthly"),
]
PLACEHOLDER = {"age": 30, "weight_kg": 70.0, "height_cm": 170.0}
PT_PLAN = re.compile(r"\bpt\b|personal ?train|\b1\s*(?:-\s*)?(?:on|to|:|-)\s*(?:-\s*)?1\b|one ?(?:to|on) ?one", re.I)
NO_WORDS = {"", "no", "n", "none", "false", "0", "-", "nil", "n/a", "na", "not set"}
YES_WORDS = {"yes", "y", "true", "x", "✓", "1"}


def pt_from(trainer, flag, membership):
    """(has_pt, known) for one row: a named trainer, a yes / number in a personal training column,
    or a personal training membership name (e.g. "PT Package", "Personal Training 3x week")."""
    flag = str(flag or "").strip().lower()
    trainer = str(trainer or "").strip()
    if trainer.lower() in YES_WORDS:                   # a yes/no column mapped as the trainer
        flag, trainer = "yes", ""
    if trainer.lower() in NO_WORDS:
        trainer = ""
    if trainer or (flag and flag not in NO_WORDS) or PT_PLAN.search(str(membership or "")):
        return True, True
    return False, bool(flag)


def _norm(h):
    return re.sub(r"[\s_]+", " ", str(h).strip().lower().replace("-", " "))


def read_file(up):
    """A DataFrame from an uploaded CSV or Excel file (GymMaster exports CSV)."""
    data = up.getvalue()
    if up.name.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(data))
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(data), encoding=enc, dtype=str, keep_default_na=False)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False, encoding_errors="replace")


def guess_columns(columns):
    """{field: column or NONE}, matching exact headings first, then headings that contain the word."""
    normed = {c: _norm(c) for c in columns}
    used, out = set(), {}
    for key, _, names in FIELDS:                       # exact headings first, for every field
        hit = next((c for c in columns if normed[c] in names and c not in used), None)
        out[key] = hit or NONE
        if hit:
            used.add(hit)
    for key, _, names in FIELDS:                       # then headings that contain a known word
        if out[key] != NONE:
            continue
        hit = next((c for c in columns if c not in used and any(
            re.search(rf"\b{re.escape(n)}\b", normed[c]) for n in names if len(n) > 3)), None)
        out[key] = hit or NONE
        if hit:
            used.add(hit)
    if out["name"] != NONE and out["first"] != NONE:        # prefer first + surname when both exist
        out["name"] = NONE
    return out


def guess_plan(name):
    text = _norm(name)
    for pat, plan in PLAN_WORDS:
        if re.search(pat, text):
            return plan
    return "Monthly"


def _date(value):
    v = gw._text(value).strip()
    if not v:
        return None
    d = pd.to_datetime(v, errors="coerce", dayfirst=True)
    if pd.isna(d):
        return None
    return d.date()


def _money(value):
    v = re.sub(r"[^\d.]", "", gw._text(value))
    try:
        return float(v) if v else None
    except ValueError:
        return None


def _digits(p):
    d = re.sub(r"\D", "", gw._text(p))
    return d[-10:] if len(d) >= 7 else ""


def build_rows(df, cols, plan_map, existing, stats=None):
    """Turn the file into import rows: {action, name, email, phone, plan, fee, end, last_visit, member_id, note}."""
    by_email = {gw._text(m.get("email")).lower(): m["id"] for _, m in existing.iterrows() if gw._text(m.get("email"))}
    by_phone = {_digits(m.get("phone")): m["id"] for _, m in existing.iterrows() if _digits(m.get("phone"))}
    by_name = {gw._text(m.get("full_name")).strip().lower(): m["id"] for _, m in existing.iterrows()}
    get = lambda r, k: gw._text(r.get(cols[k])).strip() if cols.get(k, NONE) != NONE else ""
    rows, seen = [], {}
    stats = stats if stats is not None else {}
    stats["duplicates"] = 0
    today = gw.today_local()
    for _, r in df.iterrows():
        name = get(r, "name") or " ".join(x for x in (get(r, "first"), get(r, "last")) if x)
        name = re.sub(r"\s+", " ", name).strip().title() if name.isupper() or name.islower() else name.strip()
        if not name:
            continue
        email = get(r, "email").lower()
        email = email if "@" in email else ""
        phone = get(r, "phone")
        key = email or _digits(phone) or name.lower()
        dup = seen.get(key)
        member_id = by_email.get(email) if email else None
        member_id = member_id or (by_phone.get(_digits(phone)) if _digits(phone) else None) or by_name.get(name.lower())
        mname = get(r, "membership")
        plan = plan_map.get(mname, guess_plan(mname)) if mname else "Monthly"
        start, end = _date(get(r, "start")), _date(get(r, "end"))
        if end is None and start is not None:
            end = start + timedelta(days=gw.PLAN_DAYS[plan])
        price = _money(get(r, "price"))
        fee = round(price / gw.PLAN_MONTHS[plan], 2) if price else 0.0
        dob = _date(get(r, "dob"))
        age = None
        if dob and dob.year > 1900:
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            age = age if 10 <= age <= 110 else None
        last_visit = _date(get(r, "last_visit"))
        if last_visit and last_visit > today:
            last_visit = None
        weight, height = _money(get(r, "weight")), _money(get(r, "height"))
        weight = weight if weight and 20 <= weight <= 400 else None
        height = height if height and 90 <= height <= 250 else None
        photo = get(r, "photo")
        v30 = _money(get(r, "visits_30"))
        row = {"action": "Update" if member_id else "New", "member_id": member_id, "name": name,
               "email": email, "phone": phone, "plan": plan, "fee": fee, "end": end, "start": start,
               "age": age, "goal": get(r, "goal"), "last_visit": last_visit, "membership": mname,
               "member_no": get(r, "member_no"), "weight": weight, "height": height, "price": price,
               "visits_30": int(min(v30, 60)) if v30 is not None else None,
               "trainer": "" if get(r, "trainer").lower() in NO_WORDS | YES_WORDS else get(r, "trainer"),
               "has_pt": pt_from(get(r, "trainer"), get(r, "has_pt"), mname)[0],
               "pt_known": any(pt_from(get(r, "trainer"), get(r, "has_pt"), mname)),
               "photo_url": photo if photo.lower().startswith(("http://", "https://")) else ""}
        if dup is None:
            seen[key] = row
            rows.append(row)
            continue
        # Same member twice (e.g. one row per membership): merge, keeping the newest membership
        stats["duplicates"] += 1
        if row["end"] and (not dup["end"] or row["end"] > dup["end"]):
            for k in ("plan", "fee", "end", "start", "membership", "price"):
                dup[k] = row[k]
        for k, v in row.items():
            if k not in ("action", "member_id") and v not in (None, "") and dup.get(k) in (None, ""):
                dup[k] = v
        if row["last_visit"] and dup["last_visit"] and row["last_visit"] > dup["last_visit"]:
            dup["last_visit"] = row["last_visit"]
    return rows


OPTIONAL = {"plan_name", "member_no", "import_batch", "member_since", "last_renewed_on", "last_payment",
            "membership_end", "weight_kg", "height_cm", "fitness_goal", "photo", "has_pt", "pt_trainer_id"}


def _missing_column(error):
    """The optional column a database without the latest setup doesn't have, or None."""
    text = str(error)
    m = (re.search(r"Could not find the '(\w+)' column", text)
         or re.search(r'column "?(\w+)"? of relation "?members"? does not exist', text)
         or re.search(r'column members\.(\w+) does not exist', text))
    return m.group(1) if m and m.group(1) in OPTIONAL else None


def _insert_member(supabase, data):
    """Insert a member. If the database insists on a field GymMaster doesn't export (age, weight,
    height), retry with a neutral placeholder for just that field. Returns (id, placeholder_used)."""
    used = False
    for _ in range(12):
        try:
            res = supabase.table("members").insert(data).execute().data or []
            return (res[0]["id"] if res else None), used
        except Exception as error:
            m = re.search(r'null value in column "(\w+)"', str(error))
            if m and m.group(1) in PLACEHOLDER and m.group(1) not in data:
                data = {**data, m.group(1): PLACEHOLDER[m.group(1)]}
                used = True
                continue
            gone = _missing_column(error)
            if gone and gone in data:
                data = {k: v for k, v in data.items() if k != gone}
                continue
            raise
    raise RuntimeError("Could not create the member.")


def _bulk_insert_members(supabase, items):
    """Insert up to BATCH members in one request. Adds a placeholder for a column the database insists on
    (age, weight, height) and drops extra columns an older database doesn't have yet.
    Returns (ids in the same order, placeholder_used)."""
    used = False
    for _ in range(12):
        try:
            res = supabase.table("members").insert(items, default_to_null=False).execute().data or []
            return [r.get("id") for r in res], used
        except Exception as error:
            m = re.search(r'null value in column "(\w+)"', str(error))
            if m and m.group(1) in PLACEHOLDER:
                items = [{**it, m.group(1): it.get(m.group(1), PLACEHOLDER[m.group(1)])} for it in items]
                used = True
                continue
            gone = _missing_column(error)
            if gone:
                items = [{k: v for k, v in it.items() if k != gone} for it in items]
                continue
            raise
    raise RuntimeError("Could not create the members.")


def _update_member(supabase, gym_id, member_id, fields):
    for _ in range(12):
        if not fields:
            return
        try:
            supabase.table("members").update(fields).eq("id", member_id).eq("gym_id", gym_id).execute()
            return
        except Exception as error:
            gone = _missing_column(error)
            if gone and gone in fields:
                fields = {k: v for k, v in fields.items() if k != gone}
                continue
            raise


def _member_fields(r, today):
    """Columns saved on the member from one import row (beyond name, email and phone)."""
    d = {}
    if r["end"]:
        d["membership_end"] = r["end"].isoformat()
    if r.get("membership"):
        d["plan_name"] = r["membership"][:80]
    if r.get("member_no"):
        d["member_no"] = str(r["member_no"])[:40]
    if r.get("start") and r["start"] <= today:
        d["member_since"] = r["start"].isoformat()
        if r["end"]:
            # Most recent renewal = the start of the current period
            back = r["end"] - timedelta(days=gw.PLAN_DAYS[r["plan"]])
            d["last_renewed_on"] = max(r["start"], min(back, today)).isoformat()
    if r.get("price"):
        d["last_payment"] = float(r["price"])
    if r.get("pt_known") or r.get("has_pt"):           # only when the file says something about PT
        d["has_pt"] = bool(r.get("has_pt"))
    if r.get("pt_trainer_id"):
        d["pt_trainer_id"] = r["pt_trainer_id"]
    return d


def link_trainers(supabase, gym_id, rows):
    """Match each row's trainer name to Settings → Trainers, adding trainers that aren't there yet.
    Sets row["pt_trainer_id"]. Returns how many trainers were added."""
    names = {r["trainer"].strip() for r in rows if r.get("trainer")}
    if not names:
        return 0
    try:
        have = supabase.table("trainers").select("id, full_name").eq("gym_id", gym_id).execute().data or []
    except Exception:
        return 0
    ids = {gw._text(t.get("full_name")).strip().lower(): t["id"] for t in have}
    added = 0
    for n in sorted(names):
        if n.lower() in ids:
            continue
        try:
            res = supabase.table("trainers").insert({"gym_id": gym_id, "full_name": n[:80],
                                                     "specialty": "Personal trainer"}).execute().data or []
            if res:
                ids[n.lower()] = res[0]["id"]
                added += 1
        except Exception:
            pass
    for r in rows:
        if r.get("trainer"):
            r["pt_trainer_id"] = ids.get(r["trainer"].strip().lower())
    return added


def _activity_row(gym_id, mid, r, now_iso, today, hist=None):
    renew = max(0, (r["end"] - today).days) if r["end"] else 30
    last = r["last_visit"]
    if hist and hist.get("last") and (not last or hist["last"] > last):
        last = hist["last"]
    away = (today - last).days if last else 0
    if hist:
        recent, before = hist["recent"], hist["before"]
    else:
        recent = r["visits_30"] if r.get("visits_30") is not None else (1 if last and away <= 30 else 0)
        before = recent if r.get("visits_30") is not None else 0      # assume their usual pace
    return {"member_id": mid, "gym_id": gym_id, "membership_type": r["plan"], "monthly_fee": float(r["fee"] or 0),
            "days_since_last_visit": int(away), "visits_previous_30_days": int(before),
            "visits_last_30_days": int(recent), "renewal_due_days": int(renew), "pt_sessions_attended": 0,
            "updated_at": now_iso}


def run_import(supabase, gym_id, rows, update_existing=True, progress=None, history=None, batch_id=None):
    """Import in batches of 500 so thousands of members take seconds, not minutes.
    history: [(keys, datetime)] past visits from the old software (see build_history)."""
    from datetime import timezone
    trainers_added = link_trainers(supabase, gym_id, rows)
    created = updated = skipped = failed = placeholders = visits = 0
    problems = []
    today, now_iso = gw.today_local(), datetime.now(timezone.utc).isoformat()
    new = [r for r in rows if r["action"] == "New"]
    old = [r for r in rows if r["action"] == "Update"]
    steps = max(1, len(new) // BATCH + 1 + (len(old) if update_existing else 0) // 50 + 1)
    done = 0

    def tick(text):
        nonlocal done
        done += 1
        if progress:
            progress.progress(min(0.9, done / (steps + 3)), text=text)

    ready = []                               # (member_id, row) to give plans and visits to
    for start in range(0, len(new), BATCH):
        chunk = new[start:start + BATCH]
        items = []
        for r in chunk:
            d = {"gym_id": gym_id, "full_name": r["name"]}
            for k in ("email", "phone"):
                if r[k]:
                    d[k] = r[k]
            if r["age"]:
                d["age"] = int(r["age"])
            if r["goal"]:
                d["fitness_goal"] = r["goal"]
            if r.get("weight"):
                d["weight_kg"] = r["weight"]
            if r.get("height"):
                d["height_cm"] = r["height"]
            d.update(_member_fields(r, today))
            if batch_id:
                d["import_batch"] = batch_id
            items.append(d)
        try:
            ids, used = _bulk_insert_members(supabase, items)
            placeholders += len(chunk) if used else 0
            created += len(ids)
            ready += [(i, r) for i, r in zip(ids, chunk) if i]
        except Exception as batch_error:
            if "GP_MEMBER_LIMIT" in str(batch_error):       # the plan's member limit: stop, don't trickle in
                import gympulse_billing as gbill
                failed += len(new) - start
                problems.append(gbill.limit_message(batch_error))
                break
            for d, r in zip(items, chunk):            # one bad row: find it, keep the rest
                try:
                    try:
                        mid, used = _insert_member(supabase, dict(d))
                    except Exception:
                        d = {k: v for k, v in d.items() if k not in ("membership_end", "last_renewed_on",
                                                                     "member_since", "last_payment")}
                        mid, used = _insert_member(supabase, dict(d))
                    placeholders += used
                    created += 1
                    ready.append((mid, r))
                except Exception as error:
                    failed += 1
                    problems.append(f"{r['name']}: {str(error)[:120]}")
        tick(f"Creating members… {min(start + BATCH, len(new))} of {len(new)}")

    for i, r in enumerate(old):
        if not update_existing:
            skipped += 1
            continue
        fields = {k: v for k, v in (("email", r["email"]), ("phone", r["phone"])) if v}
        fields.update(_member_fields(r, today))
        try:
            _update_member(supabase, gym_id, r["member_id"], fields)
            updated += 1
            ready.append((r["member_id"], r))
        except Exception as error:
            failed += 1
            problems.append(f"{r['name']}: {str(error)[:120]}")
        if i % 50 == 49:
            tick(f"Updating members… {i + 1} of {len(old)}")

    # Past visits: match each visit to a member, so attendance continues from the old software
    per_member = {}
    if history:
        index = {}
        for mid, r in ready:
            for k in _photo_keys(r):
                index.setdefault(k, mid)
        try:
            existing = gw.fetch_all(supabase.table("members").select("id, full_name, email, phone")
                                    .eq("gym_id", gym_id).order("id"))
        except Exception:
            existing = []
        for m in existing:
            for k in (_stem(m.get("email")), _digits(m.get("phone")), _stem(m.get("full_name"))):
                if k:
                    index.setdefault(k, m["id"])
        for keys, at in history:
            mid = next((index[k] for k in keys if k in index), None)
            if mid:
                per_member.setdefault(mid, set()).add(at)
    hist = {}
    for mid, times in per_member.items():
        days = {t.date() for t in times}
        hist[mid] = {"last": max(days),
                     "recent": sum(1 for d in days if (today - d).days < 30),
                     "before": sum(1 for d in days if 30 <= (today - d).days < 60)}

    acts = [_activity_row(gym_id, mid, r, now_iso, today, hist.get(mid))
            for mid, r in ready if r["end"] or r["membership"]]
    for start in range(0, len(acts), BATCH):
        try:
            supabase.table("member_activity").upsert(acts[start:start + BATCH]).execute()
        except Exception as error:
            problems.append(f"Plans for {len(acts[start:start + BATCH])} members: {str(error)[:120]}")
    tick("Saving plans…")

    cks = []
    for mid, times in per_member.items():
        for t in times:
            cks.append((mid, t))
    for mid, r in ready:
        if r["last_visit"] and mid not in per_member:
            cks.append((mid, datetime.combine(r["last_visit"], datetime.min.time()).replace(hour=12)))
    if progress and cks:
        progress.progress(0.9, text=f"Bringing over {len(cks):,} past visits…")
    visits = save_checkins(supabase, gym_id, cks)
    tick("Recording visits…")
    photos = photo_fail = 0
    jobs = [(mid, r["photo_url"]) for mid, r in ready if mid and r.get("photo_url")]
    if jobs:
        if progress:
            progress.progress(0.95, text=f"Downloading {len(jobs)} photos…")
        photos, photo_fail = save_photos(supabase, gym_id, jobs)
    gw.bump_data_version()
    return {"created": created, "updated": updated, "skipped": skipped, "failed": failed,
            "placeholders": placeholders, "visits": visits, "problems": problems, "photos": photos,
            "photo_fail": photo_fail, "with_history": len(per_member),
            "pt_clients": sum(1 for r in rows if r.get("has_pt")), "trainers_added": trainers_added,
            "keys": {k: mid for mid, r in ready for k in _photo_keys(r) if k}}


def save_checkins(supabase, gym_id, visits):
    """visits: [(member_id, naive local datetime)]. Saves them as check-ins (source "import"); the same
    member at the same minute is never saved twice, so importing the same file again is safe.
    Returns how many were saved."""
    rows = []
    for mid, t in visits:
        at = (t if t.tzinfo else t.replace(tzinfo=gw.APP_TZ)).isoformat()
        rows.append({"gym_id": gym_id, "member_id": mid, "checked_in_at": at, "source": "import",
                     "event_id": gw.checkin_event_id(gym_id, mid, at)})
    saved = 0
    for start in range(0, len(rows), BATCH):
        chunk = rows[start:start + BATCH]
        try:
            supabase.table("checkins").upsert(chunk, on_conflict="gym_id,event_id", ignore_duplicates=True,
                                              default_to_null=False).execute()
            saved += len(chunk)
            continue
        except Exception:
            pass
        try:
            supabase.table("checkins").insert(chunk, default_to_null=False).execute()
            saved += len(chunk)
            continue
        except Exception:
            pass
        for c in chunk:                               # older table: one at a time
            try:
                if gw.record_checkin(supabase, gym_id, c["member_id"], "import",
                                     at=c["checked_in_at"]) != "duplicate":
                    saved += 1
            except Exception:
                pass
    return saved


# ------------------------------------------------------------------ visit history
HISTORY_DATE = ["date", "visit date", "check in date", "checkin date", "check in", "checkin", "check in time",
                "checked in", "checked in at", "attendance date", "date time", "datetime", "date/time", "visit",
                "visited", "timestamp", "entry time", "entry date", "scan time", "time in", "visit time",
                "attended", "attendance", "class date", "booking date"]
HISTORY_TIME = ["time", "check in time", "time in", "entry time", "visit time", "scan time"]
MAX_HISTORY = 300000


def guess_history(columns):
    """Columns of a visit / check-in history file: who (ID, email, phone or name) and when."""
    normed = {c: _norm(c) for c in columns}
    base = guess_columns(columns)
    used = {v for v in base.values() if v != NONE}
    date_col = next((c for c in columns if normed[c] in HISTORY_DATE and c not in used), None)
    if date_col is None:
        date_col = next((c for c in columns if c not in used and re.search(
            r"\b(date|check ?in|visit|attend|timestamp|scan)", normed[c])), None)
    time_col = next((c for c in columns if normed[c] in HISTORY_TIME and c != date_col), None)
    return {**base, "date": date_col or NONE, "time": time_col or NONE}


def is_history(df):
    """A visit / check-in history: has a visit date column, no plan or end date, and members repeat."""
    h = guess_history(list(df.columns))
    if h["date"] == NONE or h["end"] != NONE or h["membership"] != NONE:
        return False
    who = next((h[k] for k in ("member_no", "email", "phone", "name", "first") if h[k] != NONE), None)
    if who is None:
        return False
    vals = df[who].astype(str)
    return len(df) <= 3 or vals.nunique() < len(df)


_DATE_FORMATS = ("%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                 "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y", "%d.%m.%Y %H:%M", "%d.%m.%Y")


def _fast_dates(when):
    """Parse a column of dates quickly: try the usual export formats in one go (fast), and only fall back to
    reading each value separately (slow on big files) when none of them fits."""
    sample = when.head(200)
    for fmt in _DATE_FORMATS:
        if pd.to_datetime(sample, errors="coerce", format=fmt).notna().mean() >= 0.95:
            out = pd.to_datetime(when, errors="coerce", format=fmt)
            if out.notna().mean() >= 0.95:
                return out
    iso = when.astype(str).str.strip().str.match(r"^\d{4}-\d{1,2}-\d{1,2}")   # 2026-11-01: year first, never day-first
    out = pd.Series(pd.NaT, index=when.index, dtype="datetime64[ns]")
    zoned = iso & when.astype(str).str.strip().str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$")
    plain = iso & ~zoned
    if zoned.any():                                   # with a time zone: convert to Lagos time
        out[zoned] = pd.to_datetime(when[zoned], errors="coerce", format="ISO8601", utc=True) \
            .dt.tz_convert(gw.APP_TZ).dt.tz_localize(None).astype("datetime64[ns]")
    if plain.any():                                   # no time zone: already local time
        out[plain] = pd.to_datetime(when[plain], errors="coerce", format="ISO8601").astype("datetime64[ns]")
    if (~iso).any():
        out[~iso] = pd.to_datetime(when[~iso], errors="coerce", dayfirst=True, format="mixed").astype("datetime64[ns]")
    return out


def build_history(df, cols):
    """[(keys, naive local datetime)] for each past visit, newest first, at most MAX_HISTORY."""
    if cols.get("date", NONE) == NONE:
        return []
    when = df[cols["date"]].astype(str)
    if cols.get("time", NONE) != NONE:
        when = when + " " + df[cols["time"]].astype(str)
    stamps = _fast_dates(when)
    if getattr(stamps.dt, "tz", None) is not None:
        stamps = stamps.dt.tz_convert(gw.APP_TZ).dt.tz_localize(None)
    now = datetime.now(gw.APP_TZ).replace(tzinfo=None)
    get = lambda k: (df[cols[k]].astype(str).str.strip() if cols.get(k, NONE) != NONE
                     else pd.Series([""] * len(df), index=df.index))
    names = get("name")
    if cols.get("name", NONE) == NONE and cols.get("first", NONE) != NONE:
        names = (get("first") + " " + get("last")).str.strip()
    out = []
    for no, em, ph, nm, t in zip(get("member_no"), get("email"), get("phone"), names, stamps):
        if pd.isna(t) or t > now or t.year < 2000:
            continue
        keys = [k for k in (_stem(no), _stem(em.lower()) if "@" in em else "", _digits(ph), _stem(nm)) if k]
        if keys:
            out.append((keys, t.to_pydatetime().replace(second=0, microsecond=0)))
    out.sort(key=lambda x: x[1], reverse=True)
    return out[:MAX_HISTORY]


# ------------------------------------------------------------------ import log and undo
def log_import(supabase, gym_id, source, file_name, summary):
    """Record an import (sql/phase16_import.sql). Returns its id, or None if the table isn't set up."""
    import uuid
    batch = str(uuid.uuid4())
    try:
        supabase.table("member_imports").insert({"id": batch, "gym_id": gym_id, "source": source,
                                                 "file_name": str(file_name)[:120], "summary": summary}).execute()
        return batch
    except Exception:
        return None


def finish_import(supabase, batch, summary):
    try:
        supabase.table("member_imports").update({"summary": summary}).eq("id", batch).execute()
    except Exception:
        pass


def recent_imports(supabase, gym_id, limit=5):
    try:
        return (supabase.table("member_imports").select("*").eq("gym_id", gym_id)
                .order("created_at", desc=True).limit(limit).execute().data or [])
    except Exception:
        return None


def undo_import(supabase, gym_id, batch):
    """Remove the members an import created (with their plans and visits). Members that were only
    updated are left as they are. Returns how many members were removed."""
    ids = [m["id"] for m in gw.fetch_all(supabase.table("members").select("id").eq("gym_id", gym_id)
                                         .eq("import_batch", batch).order("id"))]
    for start in range(0, len(ids), 200):
        chunk = ids[start:start + 200]
        for table in ("checkins", "member_activity"):
            try:
                supabase.table(table).delete().eq("gym_id", gym_id).in_("member_id", chunk).execute()
            except Exception:
                pass
        supabase.table("members").delete().eq("gym_id", gym_id).in_("id", chunk).execute()
    from datetime import timezone
    supabase.table("member_imports").update({"undone_at": datetime.now(timezone.utc).isoformat()}) \
        .eq("id", batch).eq("gym_id", gym_id).execute()
    gw.bump_data_version()
    return len(ids)


# ------------------------------------------------------------------ photos
def _stem(text):
    return re.sub(r"[^a-z0-9@.]", "", str(text).lower())


def _photo_keys(r):
    """Ways a photo file can be named for this member: member number, email, phone, name."""
    keys = [_stem(r.get("member_no")), _stem(r.get("email")), _digits(r.get("phone")), _stem(r.get("name"))]
    return [k for k in keys if k]


def _download(url):
    import requests
    r = requests.get(url, timeout=12, stream=True, headers={"User-Agent": "GymPulseAI-import"})
    r.raise_for_status()
    data = r.raw.read(8 * 1024 * 1024 + 1, decode_content=True)
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("photo larger than 8 MB")
    return data


def save_photos(supabase, gym_id, jobs, workers=8):
    """jobs: [(member_id, url or raw bytes)]. Downloads (if a link), resizes to the app's photo size and
    saves each photo, 8 at a time. Returns (saved, failed)."""
    from concurrent.futures import ThreadPoolExecutor

    def one(job):
        mid, src = job
        try:
            raw = _download(src) if isinstance(src, str) else src
            photo = gw.process_photo(raw)
            supabase.table("members").update({"photo": photo}).eq("id", mid).eq("gym_id", gym_id).execute()
            return True
        except Exception:
            return False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, jobs))
    return sum(results), len(results) - sum(results)


IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif")


def read_photo_files(files):
    """{filename stem: bytes} from uploaded images and/or ZIP files (folders inside ZIPs are fine)."""
    import zipfile
    out = {}
    for f in files or []:
        name = f.name.lower()
        if name.endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(f.getvalue())) as z:
                    for info in z.infolist():
                        base = info.filename.rsplit("/", 1)[-1]
                        if info.is_dir() or base.startswith(".") or not base.lower().endswith(IMAGE_EXT):
                            continue
                        if info.file_size > 15 * 1024 * 1024:
                            continue
                        out[_stem(base.rsplit(".", 1)[0])] = z.read(info)
            except zipfile.BadZipFile:
                continue
        elif name.endswith(IMAGE_EXT):
            out[_stem(f.name.rsplit(".", 1)[0])] = f.getvalue()
    return out


def match_photos(photo_files, members, extra_keys=None):
    """[(member_id, bytes)] matched by file name: member number, email, phone or full name."""
    index = dict(extra_keys or {})
    for _, m in members.iterrows():
        for k in (_stem(m.get("email")), _digits(m.get("phone")), _stem(m.get("full_name"))):
            if k:
                index.setdefault(k, m["id"])
    jobs, unmatched = [], []
    for stem, data in photo_files.items():
        mid = index.get(stem) or index.get(_digits(stem)) if stem else None
        if mid:
            jobs.append((mid, data))
        else:
            unmatched.append(stem)
    return jobs, unmatched


SHEET_EXT = (".csv", ".xlsx", ".xls")


def read_uploads(files):
    """Sort one drop of files into spreadsheets [(name, DataFrame)] and photos {stem: bytes}.
    Spreadsheets inside a ZIP are read too, so a whole export folder can be zipped and dropped in."""
    import zipfile

    class _F:
        def __init__(self, name, data):
            self.name, self._d = name, data

        def getvalue(self):
            return self._d
    sheets, unread = [], []
    for f in files or []:
        candidates = []
        if f.name.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(f.getvalue())) as z:
                    for info in z.infolist():
                        base = info.filename.rsplit("/", 1)[-1]
                        if (not info.is_dir() and not base.startswith(".") and "__MACOSX" not in info.filename
                                and base.lower().endswith(SHEET_EXT) and info.file_size < 60 * 1024 * 1024):
                            candidates.append(_F(base, z.read(info)))
            except zipfile.BadZipFile:
                unread.append(f.name)
        elif f.name.lower().endswith(SHEET_EXT):
            candidates.append(f)
        for c in candidates:
            try:
                df = read_file(c)
                df = df.loc[:, [x for x in df.columns if str(x).strip() and not str(x).startswith("Unnamed")]]
                if not df.empty:
                    sheets.append((c.name, df))
            except Exception:
                unread.append(c.name)
    return sheets, read_photo_files(files), unread


def detect_source(columns, names=()):
    """A friendly guess at where the file came from, for the summary."""
    text = " ".join(_norm(c) for c in columns) + " " + " ".join(n.lower() for n in names)
    if "gymmaster" in text or ("surname" in text and "expiry date" in text):
        return "GymMaster"
    if "mindbody" in text or "client id" in text or "pricing option" in text:
        return "Mindbody"
    if "glofox" in text:
        return "Glofox"
    return "your file"


def _pick(store, wkey, default, options):
    """A widget's value even while it's hidden: the live widget, else the last choice, else the guess."""
    v = st.session_state.get(wkey, store.get(wkey, default))
    return v if v in options else default


def render_gymmaster_import(supabase, gym_id):
    gw.intro("Bring your members in", ":material/upload_file:",
             "Drop in the export from GymMaster, Mindbody, Glofox, Excel or any list, from 10 members to 20,000. "
             "Plans, visits and photos come with them, so everything carries on where your old software left off.")
    flash = st.session_state.pop("gm_flash", None)
    if flash:
        st.success(flash)
    errs = st.session_state.pop("gm_errors", None)
    if errs:
        st.error("These rows were not imported:\n\n" + "\n".join(f"- {e}" for e in errs[:20]))
    _render_recent(supabase, gym_id)

    with st.popover("How do I export my members?", icon=":material/help:"):
        source = st.selectbox("Where are your members now?", list(SOURCES), key="gm_source")
        st.markdown(SOURCES[source])
        st.caption("Tip: export your **visit / attendance history** too and drop both files in together, so "
                   "GymPulse AI knows who has been training and continues from there. Add a ZIP of photos named "
                   "by member ID, email, phone or name, for example 1001.jpg or Ada Obi.jpg.")
    key = st.session_state.get("gm_up_key", 0)
    ups = st.file_uploader("Drop your member file here: CSV or Excel, plus a visit history file and a ZIP of photos "
                           "if you have them (or one ZIP with everything)",
                           type=["csv", "xlsx", "xls", "zip", "jpg", "jpeg", "png", "webp", "heic"],
                           accept_multiple_files=True, key=f"gm_up_{key}")
    if not ups:
        return
    sig = (key,) + tuple((f.name, getattr(f, "size", 0)) for f in ups)
    cached = st.session_state.get("gm_parsed")
    if cached and cached[0] == sig:
        sheets, photo_files, unread, hist_parsed = cached[1:]
    else:
        st.session_state.pop("gm_parsed", None)
        with st.spinner("Reading your files… big exports with visit history can take up to a minute."):
            sheets, photo_files, unread = read_uploads(ups)
            hist_parsed = {}
            for n, d in sheets:
                if is_history(d):
                    hg = guess_history(list(d.columns))
                    hist_parsed[n] = (hg, build_history(d.fillna("").astype(str), hg))
        st.session_state["gm_parsed"] = (sig, sheets, photo_files, unread, hist_parsed)
    if unread:
        st.warning("Couldn't read: " + ", ".join(unread[:5]) + ". Save it as CSV and try again.")
    member_sheets = [(n, d) for n, d in sheets if n not in hist_parsed]
    hist_sheets = [(n, d) for n, d in sheets if n in hist_parsed]
    if not member_sheets:
        st.info("Add the member list (CSV or Excel) as well." if (hist_sheets or photo_files) else
                "No member list found in what you dropped in. Export it as CSV or Excel and try again.")
        return
    df = pd.concat([d for _, d in member_sheets], ignore_index=True, sort=False).fillna("").astype(str)
    if len(df) > MAX_ROWS:
        st.error(f"Please upload {MAX_ROWS:,} members or fewer at a time (split the file in two).")
        return
    names = [n for n, _ in sheets]
    origin = detect_source(list(df.columns), names)
    store = st.session_state.setdefault(f"gm_choices_{key}", {})

    # Columns and plans: guessed automatically, changeable under "Review the matching"
    guess = guess_columns(list(df.columns))
    options = [NONE] + list(df.columns)
    cols = {k: _pick(store, f"gm_col_{k}_{key}", guess[k] if guess[k] in options else NONE, options)
            for k, _, _ in FIELDS}
    if cols["name"] == NONE and cols["first"] == NONE:
        st.warning("Choose the column with the members' names under **Review the matching** below.")
    plan_names = (sorted({v.strip() for v in df[cols["membership"]] if v.strip()})
                  if cols["membership"] != NONE else [])
    plan_map = {n: _pick(store, f"gm_plan_{i}_{key}", guess_plan(n), gw.PLANS) for i, n in enumerate(plan_names[:60])}

    existing = pd.DataFrame(gw.fetch_all(supabase.table("members").select("id, full_name, email, phone")
                                         .eq("gym_id", gym_id).order("id")))
    if existing.empty:
        existing = pd.DataFrame(columns=["id", "full_name", "email", "phone"])
    stats = {}
    rows = build_rows(df, cols, plan_map, existing, stats) if (cols["name"] != NONE or cols["first"] != NONE) else []

    history, hcols_all = [], []
    for n, d in hist_sheets:
        hg, parsed = hist_parsed[n]
        hcols_all.append((n, d, hg))
        history += parsed

    # Who the visits and photos belong to (preview: rows in the file + members already here)
    index = {}
    for i, r in enumerate(rows):
        for k in _photo_keys(r):
            index.setdefault(k, ("row", i))
    for _, m in existing.iterrows():
        for k in (_stem(m.get("email")), _digits(m.get("phone")), _stem(m.get("full_name"))):
            if k:
                index.setdefault(k, ("old", m["id"]))
    visits_by = {}
    for keys, t in history:
        who = next((index[k] for k in keys if k in index), None)
        if who:
            visits_by.setdefault(who, set()).add(t)
    n_visits = sum(len(v) for v in visits_by.values())
    unmatched_visits = len(history) - n_visits
    photo_hits = {s_: index.get(s_) or index.get(_digits(s_)) for s_ in photo_files}
    n_photos = sum(1 for r in rows if r.get("photo_url")) + sum(1 for v in photo_hits.values() if v)

    if not rows:
        if cols["name"] != NONE or cols["first"] != NONE:
            st.warning("No members with a name were found in the file.")
        _render_matching(df, cols, plan_names, plan_map, key, store, hcols_all, force=True)
        return

    today = gw.today_local()
    with_plan = sum(1 for r in rows if r["membership"] or r["end"])
    active = sum(1 for r in rows if r["end"] and r["end"] >= today)
    ended = sum(1 for r in rows if r["end"] and r["end"] < today)
    new = sum(r["action"] == "New" for r in rows)
    parts = [f"<b>{len(rows):,}</b> member{'s' if len(rows) != 1 else ''}",
             f"<b>{with_plan:,}</b> with plans"]
    if history or any(r["last_visit"] or r.get("visits_30") for r in rows):
        parts.append(f"<b>{n_visits:,}</b> past visits" if history else
                     f"<b>{sum(1 for r in rows if r['last_visit']):,}</b> with a last visit")
    if n_photos:
        parts.append(f"<b>{n_photos:,}</b> photo{'s' if n_photos != 1 else ''} found")
    if stats.get("duplicates"):
        parts.append(f"<b>{stats['duplicates']:,}</b> duplicate{'s' if stats['duplicates'] != 1 else ''} merged")
    gw._md('<div class="gm-sum"><div class="gm-sum-k">Ready to import from ' + gw._esc(origin) + '</div>'
           '<div class="gm-sum-v">' + " · ".join(parts) + '</div></div>')
    gw.kpi_row([("New members", f"{new:,}", "lime", "will be created"),
                ("Already in GymPulse", f"{len(rows) - new:,}", "cyan", "matched by email, phone or name"),
                ("Active plans", f"{active:,}", "amber", "go on the Risk Radar"),
                ("Ended plans", f"{ended:,}", "grey", "ready for win-back messages")])

    # Plans by type, with the plan names from the old software kept
    if with_plan:
        groups = {}
        for r in rows:
            if not (r["membership"] or r["end"]):
                continue
            g = groups.setdefault((r["membership"] or "(no plan name)", r["plan"]), [0, 0, 0])
            g[0] += 1
            g[1] += bool(r["end"] and r["end"] >= today)
            g[2] += bool(r["end"] and r["end"] < today)
        prow = [{"Plan in " + ("your file" if origin == "your file" else origin): n, "Plan type": t,
                 "Members": c, "Active": a, "Ended": e}
                for (n, t), (c, a, e) in sorted(groups.items(), key=lambda x: (gw.PLANS.index(x[0][1]), -x[1][0]))]
        st.markdown('<div class="section-label">PLANS</div>', unsafe_allow_html=True)
        gw.table(prow[:40], max_height=320,
                 caption=("Each member keeps their plan name from your old software and gets the matching plan "
                          "type, so renewals and reminders run on the right dates."
                          + (f" Showing 40 of {len(prow)} plans." if len(prow) > 40 else "")))
    no_plan = len(rows) - with_plan
    if no_plan:
        st.caption(f"{no_plan:,} member(s) have no plan or end date in the file. They'll still be imported; add "
                   "their plan later on the Risk Radar.")
    if history and unmatched_visits:
        st.caption(f"{unmatched_visits:,} visit(s) in the history didn't match any member and will be skipped.")
    unmatched_ph = [s_ for s_, v in photo_hits.items() if not v]
    if unmatched_ph:
        st.caption(f"{len(unmatched_ph)} photo(s) didn't match a member by file name: "
                   + ", ".join(unmatched_ph[:5]) + ("…" if len(unmatched_ph) > 5 else ""))

    update = _render_matching(df, cols, plan_names, plan_map, key, store, hcols_all, rows=rows,
                              visits_by=visits_by)

    import gympulse_billing as gbill
    can_add, why_full = gbill.can_add_members(supabase, gym_id, adding=new or 1)
    if not can_add and new:
        st.info(why_full + f" The {new:,} new member(s) in this file will be skipped; existing members are still "
                           "updated.")
        rows = [r for r in rows if r["action"] != "New"]
    if rows and st.button(f"Import {len(rows):,} member{'s' if len(rows) != 1 else ''}", type="primary",
                 icon=":material/upload:", key=f"gm_go_{key}", use_container_width=True):
        bar = st.progress(0.0, text="Importing…")
        summary = {"members": len(rows), "with_plans": with_plan, "visits": n_visits, "photos": n_photos,
                   "duplicates": stats.get("duplicates", 0), "files": names[:10]}
        batch = log_import(supabase, gym_id, origin, ", ".join(names)[:120], summary)
        res = run_import(supabase, gym_id, rows, update, bar, history=history, batch_id=batch)
        if photo_files:
            bar.progress(0.97, text="Adding photos…")
            fresh = pd.DataFrame(gw.fetch_all(supabase.table("members").select("id, full_name, email, phone")
                                              .eq("gym_id", gym_id).order("id")))
            jobs, unmatched = match_photos(photo_files, fresh, res["keys"]) if not fresh.empty else ([], list(photo_files))
            ok, bad = save_photos(supabase, gym_id, jobs)
            res["photos"] += ok
            res["photo_fail"] += bad + len(unmatched)
        bar.empty()
        if batch:
            finish_import(supabase, batch, {**summary, "created": res["created"], "updated": res["updated"],
                                            "visits_saved": res["visits"], "photos_saved": res["photos"],
                                            "failed": res["failed"]})
        msg = (f"Done! {res['created']:,} new member(s), {res['updated']:,} updated"
               + (f", {res['skipped']} skipped" if res["skipped"] else "")
               + (f", {res['visits']:,} past visits brought over" if res["visits"] else "")
               + (f", {res['photos']} photos added" if res.get("photos") else "") + ".")
        if res.get("pt_clients"):
            msg += (f" {res['pt_clients']:,} personal training client(s) marked, so they won't be offered a trainer"
                    + (f"; {res['trainers_added']} trainer(s) added to Settings → Trainers" if res.get("trainers_added")
                       else "") + ".")
        if res.get("photo_fail"):
            msg += (f" {res['photo_fail']} photo(s) couldn't be added (the link needed a login, or no member matched "
                    "the file name); add them on the member's profile or with Add photos below.")
        if res["placeholders"]:
            msg += (f" {res['placeholders']} member(s) got a placeholder age, weight or height because the file "
                    "didn't include them; you can update these on their profiles.")
        if res["failed"]:
            st.session_state["gm_errors"] = res["problems"]
            msg += f" {res['failed']} could not be imported (see below)."
        if batch:
            msg += " Something look wrong? Undo this import under Recent imports."
        st.session_state["gm_flash"] = msg
        st.session_state.pop(f"gm_choices_{key}", None)
        st.session_state.pop("gm_parsed", None)
        st.session_state["gm_up_key"] = key + 1
        st.rerun()


def _render_matching(df, cols, plan_names, plan_map, key, store, hcols_all, rows=None, visits_by=None, force=False):
    """The details, tucked away: column matching, plan matching, a sample of members. Returns update choice."""
    show = st.toggle("Review the matching (columns, plans and a sample of members)", value=force,
                     key=f"gm_review_{key}")
    upd_key = f"gm_upd_{key}"
    if not show:
        return store.get(upd_key, True)
    options = [NONE] + list(df.columns)
    st.markdown("**Columns**")
    st.caption("We matched these automatically. Change any that are wrong.")
    grid = st.columns(3)
    for i, (k, label, _) in enumerate(FIELDS):
        wk = f"gm_col_{k}_{key}"
        store[wk] = grid[i % 3].selectbox(label, options, index=options.index(cols[k]), key=wk)
    for n, d, hg in hcols_all:
        found = [f"{lbl}: {hg[k]}" for k, lbl in (("date", "visit date"), ("time", "time"), ("member_no", "member ID"),
                                                   ("email", "email"), ("phone", "phone"), ("name", "name"),
                                                   ("first", "first name")) if hg.get(k, NONE) != NONE]
        st.caption(f"Visit history **{n}** ({len(d):,} rows) · " + ", ".join(found))
    if plan_names:
        st.markdown("**Plans**")
        st.caption("Each plan name from your old software, and the GymPulse plan type it becomes.")
        grid = st.columns(3)
        for i, n in enumerate(plan_names[:60]):
            wk = f"gm_plan_{i}_{key}"
            store[wk] = grid[i % 3].selectbox(n, gw.PLANS, index=gw.PLANS.index(plan_map[n]), key=wk)
        if len(plan_names) > 60:
            st.caption("More than 60 plan names: the rest are matched automatically.")
    if rows:
        st.markdown("**Sample**")
        def visits(i, r):
            v = len(visits_by.get(("row", i), ())) if visits_by else 0
            if not v and r.get("member_id") and visits_by:
                v = len(visits_by.get(("old", r["member_id"]), ()))
            return f"{v:,}" if v else (f"last {r['last_visit']:%d %b}" if r["last_visit"] else "–")
        gw.table([{"Member": r["name"], "Phone": r["phone"] or "–", "Plan": r["membership"] or "–",
                   "Type": r["plan"], "Ends": f"{r['end']:%d %b %Y}" if r["end"] else "–",
                   "Visits": visits(i, r), "Photo": "Yes" if r.get("photo_url") else "–", "Action": r["action"]}
                  for i, r in enumerate(rows[:15])],
                 pills={"Action": {"New": "lime", "Update": "cyan"}},
                 caption=f"Showing the first {min(15, len(rows))} of {len(rows):,}.")
    store[upd_key] = st.checkbox("Update members who are already in GymPulse (contact details, plan and end date)",
                                 value=store.get(upd_key, True), key=upd_key)
    return store[upd_key]


def _render_recent(supabase, gym_id):
    rows = recent_imports(supabase, gym_id)
    if not rows:
        return
    st.markdown('<div class="section-label">RECENT IMPORTS</div>', unsafe_allow_html=True)
    for r in rows[:3]:
        sm = r.get("summary") or {}
        when = str(r.get("created_at") or "")[:16].replace("T", " ")
        c1, c2 = st.columns([4, 1], vertical_alignment="center")
        txt = (f"**{when}** · {gw._esc(r.get('source') or 'file')} · {sm.get('created', sm.get('members', 0)):,} new, "
               f"{sm.get('updated', 0):,} updated, {sm.get('visits_saved', 0):,} visits, "
               f"{sm.get('photos_saved', 0):,} photos")
        if r.get("undone_at"):
            c1.markdown(f"~~{txt}~~ · undone")
            continue
        c1.markdown(txt)
        if st.session_state.get("role") == "staff":
            continue
        ck = f"gm_undo_ask_{r['id']}"
        if not st.session_state.get(ck):
            if c2.button("Undo", key=f"gm_undo_{r['id']}", use_container_width=True):
                st.session_state[ck] = True
                st.rerun()
        else:
            st.warning("This removes the members this import created, with their plans and visits. Members that "
                       "were only updated keep their changes.")
            b1, b2 = st.columns(2)
            if b1.button("Yes, undo the import", type="primary", key=f"gm_undo_yes_{r['id']}",
                         use_container_width=True):
                try:
                    n = undo_import(supabase, gym_id, r["id"])
                    st.session_state["gm_flash"] = f"Import undone: {n:,} member(s) removed."
                except Exception as error:
                    st.session_state["gm_errors"] = [f"Undo didn't finish: {str(error)[:160]}"]
                st.session_state.pop(ck, None)
                st.rerun()
            if b2.button("Cancel", key=f"gm_undo_no_{r['id']}", use_container_width=True):
                st.session_state.pop(ck, None)
                st.rerun()


def render_photo_bulk(supabase, gym_id):
    """Add photos to existing members in one go, any time."""
    st.markdown("**Add photos for members you already have**")
    st.caption("Upload a ZIP (or the image files) named by member ID from your old software, email, phone or "
               "full name, for example 1001.jpg, 08031112222.jpg or Ada Obi.jpg. Member ID is safest, because two "
               "members can share a name. Photos are resized to keep the app fast.")
    key = st.session_state.get("ph_up_key", 0)
    files = st.file_uploader("Photos (ZIP or images)", type=["zip", "jpg", "jpeg", "png", "webp", "heic"],
                             accept_multiple_files=True, key=f"ph_up_{key}")
    if not files:
        return
    photos = read_photo_files(files)
    try:                                            # member_no: the ID from the old software (phase 16)
        rows = gw.fetch_all(supabase.table("members").select("id, full_name, email, phone, member_no")
                            .eq("gym_id", gym_id).order("id"))
    except Exception:
        rows = gw.fetch_all(supabase.table("members").select("id, full_name, email, phone")
                            .eq("gym_id", gym_id).order("id"))
    members = pd.DataFrame(rows)
    if members.empty or not photos:
        st.info("No photos or no members to match.")
        return
    by_no = {}
    if "member_no" in members.columns:
        for mid, no in zip(members["id"], members["member_no"]):
            if _stem(no):
                by_no.setdefault(_stem(no), mid)
    jobs, unmatched = match_photos(photos, members, by_no)
    st.caption(f"{len(photos)} photo(s): {len(jobs)} matched to a member"
               + (f", {len(unmatched)} not matched ({', '.join(unmatched[:5])}{'…' if len(unmatched) > 5 else ''})"
                  if unmatched else "") + ".")
    if jobs and st.button(f"Add {len(jobs)} photo{'s' if len(jobs) != 1 else ''}", type="primary", key=f"ph_go_{key}"):
        with st.spinner("Adding photos…"):
            ok, bad = save_photos(supabase, gym_id, jobs)
        gw.bump_data_version()
        st.session_state["gm_flash"] = f"{ok} photo(s) added." + (f" {bad} couldn't be read." if bad else "")
        st.session_state["ph_up_key"] = key + 1
        st.rerun()


render_import = render_gymmaster_import
