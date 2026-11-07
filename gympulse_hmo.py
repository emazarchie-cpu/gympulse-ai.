"""GymPulse AI · HMO members (health plans and companies that pay for their staff's gym access).

Members of an HMO (Reliance, Hygeia, AXA Mansard, Leadway, Avon…) check in by scanning the gym's HMO QR code:
usegympulseai.com/?hmo=<gym code>. The first time they type their HMO ID or phone number; after that they get a
personal one-tap link (save it to the home screen) and check in with a single tap. Each visit is saved with
source "hmo", so the gym has a monthly visits report per HMO for claims, with no paper register.

Owner side (Grow → HMO): the QR code, import the HMO's member list (CSV or Excel), add one member, the
monthly visits report (download per HMO) and covers ending soon.
Database: sql/phase28_referrals_hmo.sql.
"""
import io
import re
from datetime import date, timedelta

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

SQL_HINT = ("HMO members need a one-time setup: open Supabase, go to SQL Editor, paste in the file "
            "sql/phase28_referrals_hmo.sql and press Run.")
COMMON = ["Reliance HMO", "Hygeia HMO", "AXA Mansard Health", "Leadway Health", "Avon HMO", "AIICO Multishield",
          "Clearline HMO", "Total Health Trust", "Redcare HMO", "Wellness HMO"]
COLS = {
    "name": ["name", "full name", "member name", "enrollee name", "enrollee", "staff name", "employee name"],
    "first": ["first name", "firstname", "given name"],
    "last": ["surname", "last name", "lastname"],
    "phone": ["phone", "mobile", "phone number", "mobile number", "whatsapp", "telephone", "gsm"],
    "email": ["email", "email address", "e-mail"],
    "provider": ["hmo", "provider", "hmo name", "hmo provider", "insurer", "health plan", "plan provider"],
    "hmo_id": ["hmo id", "enrollee id", "enrolee id", "member id", "policy number", "policy no", "id", "hmo number",
               "enrollee number", "card number", "membership number", "staff id"],
    "employer": ["employer", "company", "organisation", "organization", "company name", "employer name"],
    "valid": ["valid until", "expiry", "expiry date", "end date", "cover end", "expires", "valid to", "end"],
}


def link_for(code):
    return f"{gw.APP_URL}/?hmo={code}"


def _ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


# ------------------------------------------------------------------ public check-in page
def render_public(supabase, code, token=None):
    import gympulse_booking as gb
    gb._header()
    col = gw.center("hmo", 560)
    with col:
        try:
            info = supabase.rpc("gp_hmo_info", {"p_code": str(code)}).execute().data or []
        except Exception:
            info = []
        gym = (info[0] or {}).get("business_name") if info else None
        if not gym:
            st.error("This check-in code isn't active. Please ask the front desk.")
            return
        gw._md(f'<div class="bk-title">Check in at {gw._esc(gym)}</div>'
               '<div class="bk-sub">For members whose gym access is paid by their HMO or company.</div>')
        res = st.session_state.pop("hmo_res", None)
        if res:
            _result(res, code)
            return
        tries = st.session_state.get("hmo_tries", 0)
        if token:
            if st.button("Check in now", type="primary", icon=":material/how_to_reg:", use_container_width=True,
                         key="hmo_tap"):
                _run(supabase, code, None, token)
            st.caption("Not you? Ask the front desk.")
            return
        with st.form("hmo_form"):
            key = st.text_input("Your HMO ID or phone number", placeholder="e.g. RL-20391 or 0803 000 0000")
            go = st.form_submit_button("Check in", type="primary", use_container_width=True)
        if go:
            if tries >= 8:
                st.error("Too many tries. Please ask the front desk to check you in.")
            elif len(key.strip()) < 3:
                st.error("Type your HMO ID or phone number.")
            else:
                st.session_state["hmo_tries"] = tries + 1
                _run(supabase, code, key.strip(), None)


def _run(supabase, code, key, token):
    try:
        rows = supabase.rpc("gp_hmo_checkin", {"p_code": str(code), "p_key": key, "p_token": token}).execute().data
    except Exception:
        rows = None
    r = rows[0] if isinstance(rows, list) and rows else None
    st.session_state["hmo_res"] = r or {"status": "error"}
    st.rerun()


def _result(r, code):
    status = r.get("status")
    first = gw._text(r.get("first_name"), "")
    if status in ("ok", "already"):
        n = int(r.get("visits_month") or 0)
        title = "You're checked in" if status == "ok" else "Already checked in"
        gw._md(f'<div class="bk-title" style="font-size:30px">{title}'
               f'{", " + gw._esc(first) if first else ""} ✅</div>'
               f'<div class="bk-sub">{gw._esc(r.get("provider") or "HMO")} · your {_ordinal(max(n, 1))} visit this month. '
               'Have a great session! 💪</div>')
        if r.get("token"):
            st.markdown("**Next time, check in with one tap**")
            st.caption("Open this link and add it to your home screen (Share → Add to Home Screen). It's yours only.")
            st.link_button("Open my one-tap check-in", f"{link_for(code)}&t={r['token']}", use_container_width=True,
                           icon=":material/bolt:")
    elif status == "expired":
        st.warning(f"{('Hi ' + first + ', your') if first else 'Your'} HMO cover with us has ended. Please see the "
                   "front desk to renew or update it.")
    elif status == "not_found":
        st.warning("We couldn't find you on our HMO list. Please see the front desk: they'll add you in a minute.")
        st.button("Try again", key="hmo_again", use_container_width=True)
    else:
        st.error("Check-in isn't available right now. Please ask the front desk.")
        st.button("Try again", key="hmo_again2", use_container_width=True)


# ------------------------------------------------------------------ owner: Grow → HMO
def _ready(supabase, gym_id):
    try:
        supabase.table("members").select("hmo_provider").eq("gym_id", gym_id).limit(1).execute()
        return True
    except Exception:
        return False


def _hmo_members(supabase, gym_id):
    rows = gw.fetch_all(supabase.table("members").select(
        "id, full_name, phone, email, hmo_provider, hmo_id, hmo_employer, hmo_valid_until, membership_end, archived")
        .eq("gym_id", gym_id).order("id"))
    return [r for r in rows if r.get("hmo_provider") and not r.get("archived")]


def render_owner(supabase, gym_id):
    gw.intro("HMO members", ":material/health_and_safety:",
             "Members whose gym access is paid by their HMO or company check in by scanning your HMO QR code: no "
             "paper register. Every visit is counted per HMO, ready for your monthly claims.")
    if not _ready(supabase, gym_id):
        st.info(SQL_HINT)
        return
    import gympulse_signup as gsign
    g = gsign._gym(supabase, gym_id) or {}
    code = g.get("join_code")
    hm = _hmo_members(supabase, gym_id)
    today = gw.today_local()
    ending = [r for r in hm if r.get("hmo_valid_until") and today <= date.fromisoformat(str(r["hmo_valid_until"])[:10])
              <= today + timedelta(days=30)]
    month_start = today.replace(day=1)
    ck = gw.checkins_window(supabase, gym_id, (today - month_start).days + 2)
    ids = {r["id"] for r in hm}
    this_month = ck[(ck["member_id"].isin(ids)) & (ck["at"].dt.date >= month_start)] if ck is not None and len(ck) else []
    gw.kpi_row([("HMO members", f"{len(hm):,}", "cyan", "on your HMO list"),
                ("HMOs", str(len({r['hmo_provider'] for r in hm})), "lime", "providers"),
                ("Visits this month", f"{len(this_month):,}", "amber", "for your claims"),
                ("Cover ending", str(len(ending)), "red" if ending else "grey", "in the next 30 days")])

    if code:
        url = link_for(code)
        c1, c2 = st.columns([2, 1])
        with c1:
            st.markdown("**HMO check-in QR code**")
            st.caption("Print it and put it at the front desk. The first time, members type their HMO ID or phone; "
                       "then they get a one-tap check-in link for their home screen.")
            st.code(url, language=None)
            st.caption("Making a new sign-up link (Member Management) also changes this code.")
        with c2:
            png = gsign._qr_png(url)
            st.image(png, use_container_width=True)
            import gympulse_reports as rp
            rp.download_link("Download QR code", png, "gympulse-hmo-checkin-qr.png", "image/png", "hmo_qr")
    else:
        st.info("Switch on the member sign-up link in Member Management first: the HMO QR code uses the same code.")

    t1, t2, t3 = st.tabs(["Visits report", "Add HMO list", "Members"])
    with t1:
        _report(supabase, gym_id, hm)
    with t2:
        _import(supabase, gym_id, hm)
        _add_one(supabase, gym_id)
    with t3:
        _members_list(hm, ending)


def _report(supabase, gym_id, hm):
    today = gw.today_local()
    months = [(today.replace(day=1) - pd.DateOffset(months=i)).date() for i in range(6)]
    pick = st.selectbox("Month", months, format_func=lambda d: f"{d:%B %Y}", key="hmo_month")
    end = (pd.Timestamp(pick) + pd.DateOffset(months=1)).date()
    ck = gw.checkins_window(supabase, gym_id, (today - pick).days + 2)
    by = {r["id"]: r for r in hm}
    if ck is None or not len(ck) or not by:
        st.caption("No HMO visits yet.")
        return
    v = ck[ck["member_id"].isin(by) & (ck["at"].dt.date >= pick) & (ck["at"].dt.date < end)]
    v = v.drop_duplicates(["member_id", "day"])
    if v.empty:
        st.caption(f"No HMO visits in {pick:%B %Y}.")
        return
    rows = []
    for mid, grp in v.groupby("member_id"):
        r = by[mid]
        rows.append({"HMO": r["hmo_provider"], "Name": r["full_name"], "HMO ID": r.get("hmo_id") or "",
                     "Employer": r.get("hmo_employer") or "", "Visits": len(grp),
                     "Dates": ", ".join(sorted(f"{d:%d}" for d in grp["day"]))})
    df = pd.DataFrame(rows).sort_values(["HMO", "Name"])
    summary = df.groupby("HMO").agg(Members=("Name", "count"), Visits=("Visits", "sum")).reset_index()
    gw.table(summary.to_dict("records"), caption=f"HMO visits in {pick:%B %Y} (one per member per day).")
    import gympulse_reports as rp
    rp.download_link(f"Download all ({len(df)} members)", df.to_csv(index=False), f"hmo-visits-{pick:%Y-%m}.csv",
                     "text/csv", "hmo_dl_all")
    for prov, part in df.groupby("HMO"):
        rp.download_link(f"Download {prov}", part.to_csv(index=False),
                         f"hmo-visits-{re.sub(r'[^A-Za-z0-9]+', '-', prov)}-{pick:%Y-%m}.csv", "text/csv",
                         f"hmo_dl_{re.sub(r'[^A-Za-z0-9]+', '_', prov)}")
    with st.expander("See every member"):
        gw.table(df.to_dict("records"), max_height=420)


def _guess(columns):
    norm = {c: re.sub(r"[^a-z0-9 ]+", " ", str(c).lower()).strip() for c in columns}
    out, used = {}, set()
    for k, names in COLS.items():
        hit = next((c for c in columns if norm[c] in names and c not in used), None)
        out[k] = hit
        if hit:
            used.add(hit)
    return out


def _import(supabase, gym_id, hm):
    st.markdown("**Import the HMO's member list**")
    st.caption("A CSV or Excel file from the HMO or company: name, phone or email, HMO ID, and (if you have them) "
               "the HMO name, employer and cover end date. Existing members are matched by HMO ID, phone or email.")
    up = st.file_uploader("HMO list", type=["csv", "xlsx", "xls"], key="hmo_up")
    if up is None:
        return
    try:
        df = (pd.read_csv(up, dtype=str) if up.name.lower().endswith(".csv") else pd.read_excel(up, dtype=str)).fillna("")
    except Exception as error:
        st.error(f"Couldn't read that file: {error}")
        return
    cols = _guess(list(df.columns))
    if not (cols["name"] or cols["first"]):
        st.error("No name column found. Rename the column with the members' names to 'Name' and try again.")
        return
    default = None
    if not cols["provider"]:
        default = st.selectbox("Which HMO is this list from?", COMMON + ["Other"], key="hmo_prov")
        if default == "Other":
            default = st.text_input("HMO name", key="hmo_prov_other").strip()
    existing = gw.fetch_all(supabase.table("members").select("id, full_name, phone, email, hmo_id")
                            .eq("gym_id", gym_id).order("id"))
    by_hmo = {gw._text(r.get("hmo_id")).strip().lower(): r["id"] for r in existing if r.get("hmo_id")}
    by_phone = {gw.whatsapp_digits(r.get("phone"))[-10:]: r["id"] for r in existing if gw.whatsapp_digits(r.get("phone"))}
    by_email = {gw._text(r.get("email")).strip().lower(): r["id"] for r in existing if "@" in gw._text(r.get("email"))}
    rows = []
    for _, x in df.iterrows():
        get = lambda k: gw._text(x[cols[k]]).strip() if cols.get(k) else ""
        name = get("name") or f"{get('first')} {get('last')}".strip()
        if not name:
            continue
        valid = pd.to_datetime(get("valid"), errors="coerce", dayfirst=True) if get("valid") else pd.NaT
        hid, phone, email = get("hmo_id"), get("phone"), get("email").lower()
        match = (by_hmo.get(hid.lower()) if hid else None) or \
                (by_phone.get(gw.whatsapp_digits(phone)[-10:]) if gw.whatsapp_digits(phone) else None) or \
                (by_email.get(email) if "@" in email else None)
        rows.append({"id": match, "name": name, "phone": phone, "email": email if "@" in email else "",
                     "provider": get("provider") or default, "hmo_id": hid, "employer": get("employer"),
                     "valid": None if pd.isna(valid) else valid.date()})
    rows = [r for r in rows if r["provider"]]
    if not rows:
        st.warning("Choose which HMO this list is from.")
        return
    new = sum(1 for r in rows if not r["id"])
    st.write(f"**{len(rows)}** HMO members found: **{len(rows) - new}** already in GymPulse, **{new}** new.")
    if st.button(f"Import {len(rows)} HMO members", type="primary", icon=":material/upload:", key="hmo_go",
                 use_container_width=True):
        done, failed = save_rows(supabase, gym_id, rows)
        st.session_state["grow_flash"] = (f"{done} HMO member{'s' if done != 1 else ''} saved."
                                          + (f" {failed} couldn't be saved." if failed else "")
                                          + " They can check in with the HMO QR code now.")
        st.session_state.pop("hmo_up", None)
        st.rerun()


def save_rows(supabase, gym_id, rows):
    import gympulse_gymmaster as ggm
    now = pd.Timestamp.now(tz="UTC").isoformat()
    today = gw.today_local()
    done = failed = 0
    bar = st.progress(0.0, text="Saving HMO members…")
    for i, r in enumerate(rows, 1):
        fields = {"hmo_provider": r["provider"][:80], "hmo_id": (r["hmo_id"] or None),
                  "hmo_employer": (r["employer"] or None)}
        if r["valid"]:
            fields["hmo_valid_until"] = r["valid"].isoformat()
        try:
            if r["id"]:
                supabase.table("members").update(fields).eq("id", r["id"]).execute()
            else:
                data = {"gym_id": gym_id, "full_name": r["name"][:120], "phone": r["phone"] or None,
                        "email": r["email"] or None, **fields}
                if r["valid"]:
                    data["membership_end"] = r["valid"].isoformat()
                mid, _ = ggm._insert_member(supabase, data)
                if mid:
                    renew = max(0, (r["valid"] - today).days) if r["valid"] else 30
                    try:
                        supabase.table("member_activity").upsert({
                            "member_id": mid, "gym_id": gym_id, "membership_type": "Monthly", "monthly_fee": 0,
                            "days_since_last_visit": 0, "visits_previous_30_days": 0, "visits_last_30_days": 0,
                            "renewal_due_days": renew, "pt_sessions_attended": 0, "updated_at": now}).execute()
                    except Exception:
                        pass
            done += 1
        except Exception:
            failed += 1
        bar.progress(i / len(rows), text=f"Saving HMO members… {i} of {len(rows)}")
    bar.empty()
    gw.bump_data_version()
    return done, failed


def _add_one(supabase, gym_id):
    members, _ = gw.fetch_members(supabase, gym_id, archived=False, include_photo=False)
    if members.empty:
        return
    names = dict(zip(members["id"], members["full_name"]))
    with st.form("hmo_one", clear_on_submit=True):
        st.markdown("**Add one HMO member**")
        mid = st.selectbox("Member", list(names), format_func=names.get, index=None, placeholder="Choose a member")
        c1, c2 = st.columns(2)
        prov = c1.selectbox("HMO", COMMON + ["Other"])
        other = c2.text_input("HMO name (if Other)")
        c3, c4, c5 = st.columns(3)
        hid = c3.text_input("HMO ID")
        emp = c4.text_input("Employer (optional)")
        valid = c5.date_input("Cover ends (optional)", value=None)
        if st.form_submit_button("Save", type="primary"):
            provider = other.strip() if prov == "Other" else prov
            if not mid or not provider:
                st.error("Choose the member and their HMO.")
            else:
                fields = {"hmo_provider": provider, "hmo_id": hid.strip() or None, "hmo_employer": emp.strip() or None,
                          "hmo_valid_until": valid.isoformat() if valid else None}
                supabase.table("members").update(fields).eq("id", mid).execute()
                gw.bump_data_version()
                st.session_state["grow_flash"] = f"{names[mid]} is now an HMO member ({provider})."
                st.rerun()


def _members_list(hm, ending):
    if not hm:
        st.caption("No HMO members yet. Import the HMO's list or add one member.")
        return
    if ending:
        st.warning(f"{len(ending)} HMO cover{'s' if len(ending) != 1 else ''} end in the next 30 days: "
                   + ", ".join(r["full_name"] for r in ending[:6]) + ("…" if len(ending) > 6 else ""))
    gw.table([{"Name": r["full_name"], "HMO": r["hmo_provider"], "HMO ID": r.get("hmo_id") or "",
               "Employer": r.get("hmo_employer") or "", "Cover ends": str(r.get("hmo_valid_until") or "")[:10]}
              for r in sorted(hm, key=lambda r: (r["hmo_provider"], r["full_name"]))], max_height=480)
