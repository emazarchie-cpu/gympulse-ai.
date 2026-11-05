"""GymPulse AI · Import members from GymMaster.

GymMaster exports any report as a CSV file, and each gym chooses the report's
columns, so the exact headings differ from gym to gym. This importer:
  1. reads the CSV (or Excel) file,
  2. guesses which column is which from common GymMaster headings
     (First Name, Surname, Email, Mobile, Membership, Start Date, Expiry Date,
     Price, Last Visit, ...) and lets the owner correct any guess,
  3. turns each GymMaster membership name into a GymPulse plan (the owner can
     change each one),
  4. matches existing members by email, phone or name (updates them instead of
     creating duplicates),
  5. previews, then imports: creates members, sets their plan, fee and end
     date, and records their last visit so the Risk Radar starts with real data.
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
    ("name", "Full name (if one column)", ["name", "full name", "member name", "member", "fullname", "client name"]),
    ("email", "Email", ["email", "email address", "e-mail", "member email"]),
    ("phone", "Phone", ["mobile", "mobile phone", "mobile number", "cell", "cell phone", "cellphone", "phone",
                        "phone number", "contact number", "home phone", "telephone"]),
    ("dob", "Date of birth", ["date of birth", "dob", "birthday", "birth date", "birthdate"]),
    ("membership", "Membership name", ["membership", "membership type", "membership name", "plan", "membership plan",
                                       "current membership", "membership type name"]),
    ("start", "Start date", ["start date", "membership start", "start", "joined", "join date", "member since",
                             "date joined", "membership start date"]),
    ("end", "End / expiry date", ["expiry", "expiry date", "end date", "expires", "membership expiry", "membership end",
                                  "expiration date", "end", "membership expiry date", "expire date", "valid until"]),
    ("price", "Price", ["price", "cost", "fee", "amount", "membership price", "price per period", "membership cost",
                        "regular payment", "payment amount"]),
    ("last_visit", "Last visit", ["last visit", "last attendance", "last visited", "last check in", "last checkin",
                                  "last check-in", "last visit date", "last attended"]),
    ("goal", "Fitness goal", ["goal", "fitness goal", "goals"]),
]
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


def run_import(supabase, gym_id, rows, update_existing=True, progress=None):
    created = updated = skipped = failed = placeholders = visits = 0
    problems = []
    for i, r in enumerate(rows):
        try:
            if r["action"] == "Update":
                if not update_existing:
                    skipped += 1
                    continue
                fields = {k: v for k, v in (("email", r["email"]), ("phone", r["phone"])) if v}
                if fields:
                    supabase.table("members").update(fields).eq("id", r["member_id"]).eq("gym_id", gym_id).execute()
                mid = r["member_id"]
                updated += 1
            else:
                data = {"gym_id": gym_id, "full_name": r["name"]}
                for k in ("email", "phone"):
                    if r[k]:
                        data[k] = r[k]
                if r["age"]:
                    data["age"] = int(r["age"])
                if r["goal"]:
                    data["fitness_goal"] = r["goal"]
                mid, used = _insert_member(supabase, data)
                placeholders += used
                created += 1
            if mid and r["end"]:
                gw.save_membership(supabase, gym_id, mid, r["plan"], r["fee"], r["end"])
            if mid and r["last_visit"]:
                at = datetime.combine(r["last_visit"], datetime.min.time()).replace(hour=12, tzinfo=gw.APP_TZ)
                if gw.record_checkin(supabase, gym_id, mid, "import", at=at.isoformat()) != "duplicate":
                    visits += 1
        except Exception as error:
            failed += 1
            problems.append(f"{r['name']}: {str(error)[:120]}")
        if progress:
            progress.progress((i + 1) / len(rows), text=f"Importing… {i + 1} of {len(rows)}")
    gw.bump_data_version()
    return {"created": created, "updated": updated, "skipped": skipped, "failed": failed,
            "placeholders": placeholders, "visits": visits, "problems": problems}


def render_gymmaster_import(supabase, gym_id):
    gw.intro("Import from GymMaster", ":material/upload_file:",
             "Bring your members across from GymMaster in a few minutes. GymMaster keeps running as usual; "
             "GymPulse AI adds the retention tools on top.")
    flash = st.session_state.pop("gm_flash", None)
    if flash:
        st.success(flash)
    errs = st.session_state.pop("gm_errors", None)
    if errs:
        st.error("These rows were not imported:\n\n" + "\n".join(f"- {e}" for e in errs[:20]))
    with st.popover("How to export from GymMaster", icon=":material/help:"):
        st.markdown(
            "1. In GymMaster, open **Reports** and run a member report (for example a member list or "
            "memberships report).\n"
            "2. Use **Add Column** to include: **First Name, Surname, Email, Mobile, Membership, Start Date, "
            "Expiry Date, Price** and, if available, **Last Visit**.\n"
            "3. Choose **Export to CSV** and upload the file below.\n\n"
            "Different headings are fine: you'll confirm which column is which before anything is imported.")
    key = st.session_state.get("gm_up_key", 0)
    up = st.file_uploader("GymMaster export (CSV or Excel)", type=["csv", "xlsx", "xls"], key=f"gm_up_{key}")
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
    if len(df) > 3000:
        st.error("Please upload 3,000 members or fewer at a time.")
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
            st.markdown("**2. Match each GymMaster membership to a plan**")
            grid = st.columns(3)
            for i, n in enumerate(names[:60]):
                g = guess_plan(n)
                plan_map[n] = grid[i % 3].selectbox(n, gw.PLANS, index=gw.PLANS.index(g), key=f"gm_plan_{i}_{key}")
            if len(names) > 60:
                st.caption("More than 60 membership names: the rest are matched automatically.")

    # 3. preview
    existing = pd.DataFrame(supabase.table("members").select("id, full_name, email, phone").eq("gym_id", gym_id)
                            .execute().data or [])
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
        msg = (f"Imported from GymMaster: {res['created']} new, {res['updated']} updated"
               + (f", {res['skipped']} skipped" if res["skipped"] else "")
               + (f", {res['visits']} last visits recorded" if res["visits"] else "") + ".")
        if res["placeholders"]:
            msg += (f" {res['placeholders']} member(s) got a placeholder age, weight or height because GymMaster "
                    "didn't include them; you can update these on their profiles.")
        if res["failed"]:
            st.session_state["gm_errors"] = res["problems"]
            msg += f" {res['failed']} could not be imported (see below)."
        st.session_state["gm_flash"] = msg
        st.session_state["gm_up_key"] = key + 1
        st.rerun()
