"""GymPulse AI · Bring members in from any software or spreadsheet.

Works with GymMaster, Mindbody, Glofox, Spark, Excel / Google Sheets or any
CSV: each system names its columns differently (and GymMaster lets every gym
pick its own), so the importer:
  1. reads the CSV or Excel file (up to 20,000 members),
  2. guesses which column is which from common headings and lets the owner
     correct any guess,
  3. turns each membership name into a GymPulse plan (editable),
  4. matches existing members by email, phone or name (updates, no duplicates),
  5. previews, then imports in batches of 500: creates members with their plan,
     fee and end date, and records their last visit so the Risk Radar starts
     with real data.
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
    for key, _, names in FIELDS:
        hit = next((c for c in columns if normed[c] in names and c not in used), None)
        if hit is None:
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


def build_rows(df, cols, plan_map, existing):
    """Turn the file into import rows: {action, name, email, phone, plan, fee, end, last_visit, member_id, note}."""
    by_email = {gw._text(m.get("email")).lower(): m["id"] for _, m in existing.iterrows() if gw._text(m.get("email"))}
    by_phone = {_digits(m.get("phone")): m["id"] for _, m in existing.iterrows() if _digits(m.get("phone"))}
    by_name = {gw._text(m.get("full_name")).strip().lower(): m["id"] for _, m in existing.iterrows()}
    get = lambda r, k: gw._text(r.get(cols[k])).strip() if cols.get(k, NONE) != NONE else ""
    rows, seen = [], set()
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
        if key in seen:
            continue
        seen.add(key)
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
        rows.append({"action": "Update" if member_id else "New", "member_id": member_id, "name": name,
                     "email": email, "phone": phone, "plan": plan, "fee": fee, "end": end, "start": start,
                     "age": age, "goal": get(r, "goal"), "last_visit": last_visit, "membership": mname})
    return rows


def _insert_member(supabase, data):
    """Insert a member. If the database insists on a field GymMaster doesn't export (age, weight,
    height), retry with a neutral placeholder for just that field. Returns (id, placeholder_used)."""
    used = False
    for _ in range(4):
        try:
            res = supabase.table("members").insert(data).execute().data or []
            return (res[0]["id"] if res else None), used
        except Exception as error:
            m = re.search(r'null value in column "(\w+)"', str(error))
            if m and m.group(1) in PLACEHOLDER and m.group(1) not in data:
                data = {**data, m.group(1): PLACEHOLDER[m.group(1)]}
                used = True
                continue
            raise
    raise RuntimeError("Could not create the member.")


def _bulk_insert_members(supabase, items):
    """Insert up to BATCH members in one request. Adds a placeholder for a column the database insists on
    (age, weight, height) if needed. Returns (ids in the same order, placeholder_used)."""
    used = False
    for _ in range(4):
        try:
            res = supabase.table("members").insert(items, default_to_null=False).execute().data or []
            return [r.get("id") for r in res], used
        except Exception as error:
            m = re.search(r'null value in column "(\w+)"', str(error))
            if m and m.group(1) in PLACEHOLDER:
                items = [{**it, m.group(1): it.get(m.group(1), PLACEHOLDER[m.group(1)])} for it in items]
                used = True
                continue
            raise
    raise RuntimeError("Could not create the members.")


def _activity_row(gym_id, mid, r, now_iso, today):
    renew = max(0, (r["end"] - today).days) if r["end"] else 30
    away = (today - r["last_visit"]).days if r["last_visit"] else 0
    return {"member_id": mid, "gym_id": gym_id, "membership_type": r["plan"], "monthly_fee": float(r["fee"] or 0),
            "days_since_last_visit": int(away), "visits_previous_30_days": 0,
            "visits_last_30_days": 1 if r["last_visit"] and away <= 30 else 0,
            "renewal_due_days": int(renew), "pt_sessions_attended": 0, "updated_at": now_iso}


def run_import(supabase, gym_id, rows, update_existing=True, progress=None):
    """Import in batches of 500 so thousands of members take seconds, not minutes."""
    from datetime import timezone
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
            progress.progress(min(1.0, done / (steps + 2)), text=text)

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
            if r["end"]:
                d["membership_end"] = r["end"].isoformat()
            items.append(d)
        try:
            ids, used = _bulk_insert_members(supabase, items)
            placeholders += len(chunk) if used else 0
            created += len(ids)
            ready += [(i, r) for i, r in zip(ids, chunk) if i]
        except Exception:
            for d, r in zip(items, chunk):            # one bad row: find it, keep the rest
                try:
                    if "membership_end" in d:
                        try:
                            mid, used = _insert_member(supabase, dict(d))
                        except Exception:
                            d.pop("membership_end")
                            mid, used = _insert_member(supabase, dict(d))
                    else:
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
        if r["end"]:
            fields["membership_end"] = r["end"].isoformat()
        try:
            if fields:
                supabase.table("members").update(fields).eq("id", r["member_id"]).eq("gym_id", gym_id).execute()
            updated += 1
            ready.append((r["member_id"], r))
        except Exception as error:
            failed += 1
            problems.append(f"{r['name']}: {str(error)[:120]}")
        if i % 50 == 49:
            tick(f"Updating members… {i + 1} of {len(old)}")

    acts = [_activity_row(gym_id, mid, r, now_iso, today) for mid, r in ready if r["end"] or r["membership"]]
    for start in range(0, len(acts), BATCH):
        try:
            supabase.table("member_activity").upsert(acts[start:start + BATCH]).execute()
        except Exception as error:
            problems.append(f"Plans for {len(acts[start:start + BATCH])} members: {str(error)[:120]}")
    tick("Saving plans…")

    cks = []
    for mid, r in ready:
        if r["last_visit"]:
            at = datetime.combine(r["last_visit"], datetime.min.time()).replace(hour=12, tzinfo=gw.APP_TZ).isoformat()
            cks.append({"gym_id": gym_id, "member_id": mid, "checked_in_at": at, "source": "import",
                        "event_id": gw.checkin_event_id(gym_id, mid, at)})
    for start in range(0, len(cks), BATCH):
        chunk = cks[start:start + BATCH]
        try:
            supabase.table("checkins").insert(chunk, default_to_null=False).execute()
            visits += len(chunk)
        except Exception:
            for c in chunk:                            # duplicates or an older table: one at a time
                try:
                    if gw.record_checkin(supabase, gym_id, c["member_id"], "import", at=c["checked_in_at"]) != "duplicate":
                        visits += 1
                except Exception:
                    pass
    tick("Recording last visits…")
    gw.bump_data_version()
    return {"created": created, "updated": updated, "skipped": skipped, "failed": failed,
            "placeholders": placeholders, "visits": visits, "problems": problems}


def render_gymmaster_import(supabase, gym_id):
    gw.intro("Bring your members in", ":material/upload_file:",
             "From GymMaster, Mindbody, Glofox, Excel or any other list, from 10 members to 20,000. Your current "
             "software can keep running; GymPulse AI adds the retention tools on top.")
    flash = st.session_state.pop("gm_flash", None)
    if flash:
        st.success(flash)
    errs = st.session_state.pop("gm_errors", None)
    if errs:
        st.error("These rows were not imported:\n\n" + "\n".join(f"- {e}" for e in errs[:20]))
    c1, c2 = st.columns([1, 2], vertical_alignment="center")
    source = c1.selectbox("Where are your members now?", list(SOURCES), key="gm_source")
    c2.caption(SOURCES[source])
    key = st.session_state.get("gm_up_key", 0)
    up = st.file_uploader("Your export or spreadsheet (CSV or Excel)", type=["csv", "xlsx", "xls"], key=f"gm_up_{key}")
    if up is None:
        return
    try:
        df = read_file(up)
    except Exception:
        st.error("That file couldn't be read. Export it from GymMaster as CSV and try again.")
        return
    df = df.loc[:, [c for c in df.columns if str(c).strip() and not str(c).startswith("Unnamed")]]
    if df.empty:
        st.error("The file has no rows.")
        return
    if len(df) > MAX_ROWS:
        st.error(f"Please upload {MAX_ROWS:,} members or fewer at a time (split the file in two).")
        return
    st.caption(f"{len(df)} rows and {len(df.columns)} columns found.")

    # 1. columns
    st.markdown("**1. Check the columns**")
    guess = guess_columns(list(df.columns))
    options = [NONE] + list(df.columns)
    cols = {}
    grid = st.columns(3)
    for i, (k, label, _) in enumerate(FIELDS):
        default = guess[k] if guess[k] in options else NONE
        cols[k] = grid[i % 3].selectbox(label, options, index=options.index(default), key=f"gm_col_{k}_{key}")
    if cols["name"] == NONE and cols["first"] == NONE:
        st.warning("Choose the column with the members' names (First name, or Full name).")
        return

    # 2. memberships -> plans
    plan_map = {}
    if cols["membership"] != NONE:
        names = sorted({gw._text(v).strip() for v in df[cols["membership"]] if gw._text(v).strip()})
        if names:
            st.markdown("**2. Match each membership to a plan**")
            grid = st.columns(3)
            for i, n in enumerate(names[:60]):
                g = guess_plan(n)
                plan_map[n] = grid[i % 3].selectbox(n, gw.PLANS, index=gw.PLANS.index(g), key=f"gm_plan_{i}_{key}")
            if len(names) > 60:
                st.caption("More than 60 membership names: the rest are matched automatically.")

    # 3. preview
    existing = pd.DataFrame(gw.fetch_all(supabase.table("members").select("id, full_name, email, phone")
                                         .eq("gym_id", gym_id).order("id")))
    if existing.empty:
        existing = pd.DataFrame(columns=["id", "full_name", "email", "phone"])
    rows = build_rows(df, cols, plan_map, existing)
    if not rows:
        st.warning("No members with a name were found in the file.")
        return
    new = sum(r["action"] == "New" for r in rows)
    st.markdown("**3. Preview**")
    gw.kpi_row([("New members", str(new), "lime", "will be created"),
                ("Already in GymPulse", str(len(rows) - new), "cyan", "matched by email, phone or name"),
                ("With an end date", str(sum(1 for r in rows if r["end"])), "amber", "go on the Risk Radar"),
                ("With a last visit", str(sum(1 for r in rows if r["last_visit"])), "grey", "recorded as a visit")])
    gw.table([{"Member": r["name"], "Email": r["email"] or "–", "Phone": r["phone"] or "–",
               "Plan": r["plan"], "Ends": f"{r['end']:%d %b %Y}" if r["end"] else "–",
               "Last visit": f"{r['last_visit']:%d %b %Y}" if r["last_visit"] else "–",
               "Action": r["action"]} for r in rows[:15]],
             pills={"Action": {"New": "lime", "Update": "cyan"}},
             caption=f"Showing the first {min(15, len(rows))} of {len(rows)}.")
    no_end = sum(1 for r in rows if not r["end"])
    if no_end:
        st.caption(f"{no_end} member(s) have no start or end date in the file. They'll be imported, and you can "
                   "add their plan later on the Risk Radar.")
    update = st.checkbox("Update members who are already in GymPulse (email, phone and plan)", value=True,
                         key=f"gm_upd_{key}")
    if st.button(f"Import {len(rows)} member{'s' if len(rows) != 1 else ''}", type="primary",
                 icon=":material/upload:", key=f"gm_go_{key}"):
        bar = st.progress(0.0, text="Importing…")
        res = run_import(supabase, gym_id, rows, update, bar)
        bar.empty()
        msg = (f"Imported from {source}: {res['created']} new, {res['updated']} updated"
               + (f", {res['skipped']} skipped" if res["skipped"] else "")
               + (f", {res['visits']} last visits recorded" if res["visits"] else "") + ".")
        if res["placeholders"]:
            msg += (f" {res['placeholders']} member(s) got a placeholder age, weight or height because the file "
                    "didn't include them; you can update these on their profiles.")
        if res["failed"]:
            st.session_state["gm_errors"] = res["problems"]
            msg += f" {res['failed']} could not be imported (see below)."
        st.session_state["gm_flash"] = msg
        st.session_state["gm_up_key"] = key + 1
        st.rerun()


render_import = render_gymmaster_import
