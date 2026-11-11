"""GymPulse AI · HMO members (health plans and companies that pay for their staff's gym access).

Members of an HMO (Reliance, Hygeia, AXA Mansard, Leadway, Avon…) check in by scanning the gym's HMO QR code:
usegympulseai.com/?hmo=<gym code>. The first time they type their HMO ID or phone number; after that they get a
personal one-tap link (save it to the home screen) and check in with a single tap. Each visit is saved with
source "hmo", so the gym has a monthly visits report per HMO for claims, with no paper register.

How HMO gym access works in Nigeria, and how this follows it:
  * Gym access comes with the enrollee's plan tier and is capped at 1, 2 or 3 sessions a week. Each member
    can have a plan and a weekly cap (or use the HMO's usual cap); the QR check-in stops a visit over the cap,
    because the HMO won't pay for it.
  * Some HMOs ask for a verification / authorisation code (from their app or by SMS) for each visit: switch
    that on per HMO and the check-in asks for it and saves it with the visit.
  * The HMO pays the gym per visit, or a fixed amount per member each month, after a monthly claim; HMOs
    often pay late. Claims: each month's amount per HMO, a claim file to send, and sent / paid / queried
    tracking with what's still owed.

Owner side (Grow → HMO): the QR code, claims, the monthly visits report, HMO settings, import the HMO's member
list (CSV or Excel), add one member, and covers ending soon.
Database: sql/phase28_referrals_hmo.sql, sql/phase37_hmo_plans_claims.sql.
"""
import io
import re
from datetime import date, timedelta

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

SQL_HINT = ("HMO members need a one-time setup: open Supabase, go to SQL Editor, paste in the file "
            "sql/phase28_referrals_hmo.sql and press Run.")
SQL37_HINT = ("HMO plans, weekly limits and claims need a one-time setup: open Supabase, go to SQL Editor, paste "
              "in the file sql/phase37_hmo_plans_claims.sql and press Run.")
PAY_MODELS = {"per_visit": "Per visit", "per_member": "Per member each month"}
CLAIM_STATUS = {"sent": "Sent", "paid": "Paid", "part_paid": "Part paid", "queried": "Queried"}
LATE_DAYS = 60            # an HMO claim unpaid this long after sending is flagged
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
    "plan": ["plan", "plan name", "plan type", "hmo plan", "package", "tier", "plan tier", "benefit plan", "category"],
    "limit": ["sessions per week", "gym sessions", "weekly sessions", "sessions week", "gym limit", "sessions",
              "gym sessions per week", "gym access"],
}


def _limit_from(text):
    """'2 sessions/week', '3', 'Gym (3 Session/Week)' -> 2 / 3 / 3; anything else -> None."""
    m = re.search(r"\d+", gw._text(text))
    n = int(m.group()) if m else 0
    return n if 0 < n <= 7 else None


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
        import gympulse_billing as gbill
        if gbill.gym_locked(gbill.gym_by("gyms", "join_code", code)):
            gbill.render_gym_locked(gym)
            return
        gw._md(f'<div class="bk-title">Check in at {gw._esc(gym)}</div>'
               '<div class="bk-sub">For members whose gym access is paid by their HMO or company.</div>')
        res = st.session_state.pop("hmo_res", None) or st.session_state.get("hmo_need")
        if res:
            _result(res, code, supabase)
            return
        tries = st.session_state.get("hmo_tries", 0)
        if token:
            if st.button("Check in now", type="primary", icon=":material/how_to_reg:", use_container_width=True,
                         key="hmo_tap"):
                st.session_state["hmo_last"] = (None, token)
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
                st.session_state["hmo_last"] = (key.strip(), None)
                _run(supabase, code, key.strip(), None)


def _run(supabase, code, key, token, hmo_code=None):
    st.session_state.pop("hmo_need", None)
    args = {"p_code": str(code), "p_key": key, "p_token": token}
    if hmo_code:
        args["p_hmo_code"] = hmo_code         # only the phase37 function takes it
    try:
        rows = supabase.rpc("gp_hmo_checkin", args).execute().data
    except Exception:
        rows = None
    r = rows[0] if isinstance(rows, list) and rows else None
    st.session_state["hmo_res"] = r or {"status": "error"}
    st.rerun()


def _week_line(r):
    lim = r.get("week_limit")
    if not lim:
        return ""
    used = int(r.get("visits_week") or 0)
    return f" · {min(used, int(lim))} of {int(lim)} HMO session{'s' if int(lim) != 1 else ''} used this week"


def _result(r, code, supabase=None):
    status = r.get("status")
    first = gw._text(r.get("first_name"), "")
    if status in ("ok", "already"):
        n = int(r.get("visits_month") or 0)
        title = "You're checked in" if status == "ok" else "Already checked in"
        gw._md(f'<div class="bk-title" style="font-size:30px">{title}'
               f'{", " + gw._esc(first) if first else ""} ✅</div>'
               f'<div class="bk-sub">{gw._esc(r.get("provider") or "HMO")} · your {_ordinal(max(n, 1))} visit this month'
               f'{gw._esc(_week_line(r))}. Have a great session! 💪</div>')
        if r.get("token"):
            st.markdown("**Next time, check in with one tap**")
            st.caption("Open this link and add it to your home screen (Share → Add to Home Screen). It's yours only.")
            st.link_button("Open my one-tap check-in", f"{link_for(code)}&t={r['token']}", use_container_width=True,
                           icon=":material/bolt:")
    elif status == "limit":
        lim = int(r.get("week_limit") or 0)
        st.warning(f"{('Hi ' + first + ', you') if first else 'You'}'ve used your {lim} HMO gym "
                   f"session{'s' if lim != 1 else ''} for this week. Your HMO sessions start again on Monday. "
                   "If you'd like to train today, the front desk can check you in as a paid visit.")
    elif status == "need_code":
        st.info(f"{('Hi ' + first + ', ') if first else ''}{gw._text(r.get('provider'), 'your HMO')} needs a code for "
                "each gym visit. Get it from your HMO's app or SMS, then type it here.")
        st.session_state["hmo_need"] = r          # keep this step on screen until they check in
        key, token = st.session_state.get("hmo_last") or (None, None)
        with st.form("hmo_code_form"):
            hcode = st.text_input("Code for today's visit", placeholder="e.g. 7781-AB")
            go = st.form_submit_button("Check in", type="primary", use_container_width=True)
        if go:
            if len(hcode.strip()) < 3:
                st.error("Type the code from your HMO.")
            elif key or token:
                _run(supabase, code, key, token, hcode.strip())
            else:
                st.error("Please start again.")
        if st.button("Start again", key="hmo_restart", type="tertiary"):
            st.session_state.pop("hmo_need", None)
            st.rerun()
        return
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
    base = "id, full_name, phone, email, hmo_provider, hmo_id, hmo_employer, hmo_valid_until, membership_end, archived"
    try:
        rows = gw.fetch_all(supabase.table("members").select(base + ", hmo_plan, hmo_weekly_limit, created_at")
                            .eq("gym_id", gym_id).order("id"))
    except Exception:                                           # phase37 not run yet
        rows = gw.fetch_all(supabase.table("members").select(base + ", created_at").eq("gym_id", gym_id).order("id"))
    return [r for r in rows if r.get("hmo_provider") and not r.get("archived")]


def load_providers(supabase, gym_id):
    """{HMO name: settings} from hmo_providers, or None when phase37 hasn't been run."""
    try:
        rows = supabase.table("hmo_providers").select("*").eq("gym_id", gym_id).execute().data or []
    except Exception:
        return None
    return {r["name"]: r for r in rows}


def load_claims(supabase, gym_id):
    try:
        return supabase.table("hmo_claims").select("*").eq("gym_id", gym_id).order("month", desc=True) \
            .execute().data or []
    except Exception:
        return None


def _date(v):
    d = pd.to_datetime(v, errors="coerce")
    return None if pd.isna(d) else d.date()


def week_limit(member, providers):
    """The member's own weekly cap, else their HMO's usual cap, else None (no cap)."""
    own = member.get("hmo_weekly_limit")
    if own is not None and not pd.isna(own) and int(own) > 0:
        return int(own)
    hp = (providers or {}).get(member.get("hmo_provider")) or {}
    v = hp.get("weekly_limit")
    return int(v) if v is not None and not pd.isna(v) and int(v) > 0 else None


def _month_checkins(supabase, gym_id, ids, start, end):
    """One row per HMO member per day between start (minus 6 days, for the first week) and end."""
    if not ids:
        return pd.DataFrame(columns=["member_id", "day", "code"])
    lo = (pd.Timestamp(start) - pd.Timedelta(days=6)).tz_localize(gw.APP_TZ).isoformat()
    hi = pd.Timestamp(end).tz_localize(gw.APP_TZ).isoformat()
    rows = None
    for cols in ("member_id, checked_in_at, hmo_code", "member_id, checked_in_at"):
        try:
            rows = gw.fetch_all(supabase.table("checkins").select(cols).eq("gym_id", gym_id)
                                .gte("checked_in_at", lo).lt("checked_in_at", hi).order("checked_in_at"))
            break
        except Exception:
            continue
    df = pd.DataFrame(rows or [])
    if df.empty:
        return pd.DataFrame(columns=["member_id", "day", "code"])
    df = df[df["member_id"].isin(ids)]
    at = pd.to_datetime(df["checked_in_at"], errors="coerce", utc=True, format="ISO8601").dt.tz_convert(gw.APP_TZ)
    df = pd.DataFrame({"member_id": df["member_id"], "day": at.dt.date,
                       "code": df["hmo_code"].fillna("") if "hmo_code" in df.columns else ""})
    # one visit per member per day; keep a code if any check-in that day had one
    df = df.sort_values("code", ascending=False).drop_duplicates(["member_id", "day"]).sort_values(["member_id", "day"])
    return df.reset_index(drop=True)


def month_visits(supabase, gym_id, hm, providers, month):
    """Every HMO visit in `month`, marked over the weekly cap or missing a code (the HMO may refuse both)."""
    start = month
    end = (pd.Timestamp(month) + pd.DateOffset(months=1)).date()
    by = {r["id"]: r for r in hm}
    ck = _month_checkins(supabase, gym_id, set(by), start, end)
    out = []
    for mid, grp in ck.groupby("member_id"):
        m = by[mid]
        lim = week_limit(m, providers)
        hp = (providers or {}).get(m["hmo_provider"]) or {}
        used = {}
        for _, v in grp.iterrows():
            wk = v["day"] - timedelta(days=v["day"].weekday())
            used[wk] = used.get(wk, 0) + 1
            if v["day"] < start:
                continue                                  # only counted towards the week's cap
            over = lim is not None and used[wk] > lim
            no_code = bool(hp.get("needs_code")) and not gw._text(v["code"])
            out.append({"member_id": mid, "HMO": m["hmo_provider"], "Name": m["full_name"],
                        "HMO ID": m.get("hmo_id") or "", "Plan": m.get("hmo_plan") or "",
                        "Employer": m.get("hmo_employer") or "", "Date": v["day"], "Code": gw._text(v["code"]),
                        "Over limit": over, "No code": no_code, "Claimable": not over and not no_code})
    return pd.DataFrame(out)


def covered_members(hm, provider, month):
    """Members of an HMO whose cover ran during `month` (for per-member-each-month HMOs)."""
    end = (pd.Timestamp(month) + pd.DateOffset(months=1)).date()
    n = 0
    for r in hm:
        if r["hmo_provider"] != provider:
            continue
        valid = _date(r.get("hmo_valid_until"))
        joined = _date(str(r.get("created_at") or "")[:10])
        if (valid is None or valid >= month) and (joined is None or joined < end):
            n += 1
    return n


def claim_figures(hm, providers, visits, month):
    """One row per HMO for the month: members, visits, refused-risk visits, claimable and the amount."""
    names = sorted({r["hmo_provider"] for r in hm})
    rows = []
    for prov in names:
        hp = (providers or {}).get(prov) or {}
        v = visits[visits["HMO"] == prov] if len(visits) else visits
        claimable = int(v["Claimable"].sum()) if len(v) else 0
        visitors = int(v[v["Claimable"]]["member_id"].nunique()) if len(v) else 0
        model = hp.get("pay_model") or "per_visit"
        rate = float(hp.get("rate") or 0)
        covered = covered_members(hm, prov, month)
        amount = rate * (claimable if model == "per_visit" else covered)
        due = (pd.Timestamp(month) + pd.DateOffset(months=1) + pd.Timedelta(days=int(hp.get("claim_days") or 30))).date()
        rows.append({"provider": prov, "model": model, "rate": rate, "members": covered if model == "per_member"
                     else visitors, "visits": int(len(v)), "over": int(v["Over limit"].sum()) if len(v) else 0,
                     "no_code": int(v["No code"].sum()) if len(v) else 0, "claimable": claimable,
                     "amount": amount, "send_by": due})
    return rows


def render_owner(supabase, gym_id):
    gw.intro("HMO members", ":material/health_and_safety:",
             "Members whose gym access is paid by their HMO check in by scanning your HMO QR code: no paper "
             "register. GymPulse keeps to each plan's weekly sessions, works out each month's claim per HMO and "
             "tracks what has been paid.")
    if not _ready(supabase, gym_id):
        st.info(SQL_HINT)
        return
    import gympulse_signup as gsign
    g = gsign._gym(supabase, gym_id) or {}
    code = g.get("join_code")
    hm = _hmo_members(supabase, gym_id)
    providers = load_providers(supabase, gym_id)
    claims = load_claims(supabase, gym_id)
    today = gw.today_local()
    ending = [r for r in hm if _date(r.get("hmo_valid_until")) and today <= _date(r["hmo_valid_until"])
              <= today + timedelta(days=30)]
    owed = sum(max(float(c.get("amount") or 0) - float(c.get("amount_paid") or 0), 0)
               for c in (claims or []) if c.get("status") != "paid")
    late = [c for c in (claims or []) if c.get("status") != "paid" and _date(c.get("sent_on"))
            and (today - _date(c["sent_on"])).days > LATE_DAYS]
    month_start = today.replace(day=1)
    this_month = month_visits(supabase, gym_id, hm, providers, month_start) if hm else pd.DataFrame()
    gw.kpi_row([("HMO members", f"{len(hm):,}", "cyan", f"{len({r['hmo_provider'] for r in hm})} HMOs"),
                ("Visits this month", f"{len(this_month):,}", "lime",
                 f"{int(this_month['Over limit'].sum())} over the weekly limit" if len(this_month) else "for your claims"),
                ("Owed by HMOs", _money(owed), "red" if late else "amber",
                 f"{len(late)} claim{'s' if len(late) != 1 else ''} unpaid {LATE_DAYS}+ days" if late else "sent, not yet paid"),
                ("Cover ending", str(len(ending)), "red" if ending else "grey", "in the next 30 days")])

    if code:
        url = link_for(code)
        c1, c2 = st.columns([2, 1])
        with c1:
            st.markdown("**HMO check-in QR code**")
            st.caption("Print it and put it at the front desk. The first time, members type their HMO ID or phone; "
                       "then they get a one-tap check-in link for their home screen. A visit over the member's weekly "
                       "sessions is stopped, and HMOs that need a code ask for it.")
            st.code(url, language=None)
            st.caption("Making a new sign-up link (Member Management) also changes this code.")
        with c2:
            png = gsign._qr_png(url)
            st.image(png, use_container_width=True)
            import gympulse_reports as rp
            rp.download_link("Download QR code", png, "gympulse-hmo-checkin-qr.png", "image/png", "hmo_qr")
    else:
        st.info("Switch on the member sign-up link in Member Management first: the HMO QR code uses the same code.")

    t1, t2, t3, t4, t5 = st.tabs(["Claims", "Visits", "HMO settings", "Add HMO list", "Members"])
    with t1:
        _claims(supabase, gym_id, hm, providers, claims)
    with t2:
        _report(supabase, gym_id, hm, providers)
    with t3:
        _settings(supabase, gym_id, hm, providers)
    with t4:
        _import(supabase, gym_id, hm)
        _add_one(supabase, gym_id, providers is not None)
    with t5:
        monday = today - timedelta(days=today.weekday())
        wk = _month_checkins(supabase, gym_id, {r["id"] for r in hm}, monday, today + timedelta(days=1))
        week = wk[wk["day"] >= monday].groupby("member_id").size().to_dict() if len(wk) else {}
        _members_list(hm, ending, providers, week)


def _money(x):
    return f"₦{float(x or 0):,.0f}"


def _months(today, n=6):
    return [(today.replace(day=1) - pd.DateOffset(months=i)).date() for i in range(n)]


# ------------------------------------------------------------------ claims
def _claims(supabase, gym_id, hm, providers, claims):
    if providers is None or claims is None:
        st.info(SQL37_HINT)
        return
    if not hm:
        st.caption("No HMO members yet. Import the HMO's list or add one member.")
        return
    today = gw.today_local()
    months = _months(today)
    pick = st.selectbox("Claim for", months, index=1 if today.day <= 20 else 0, format_func=lambda d: f"{d:%B %Y}",
                        key="hmo_claim_month", help="Claims usually go to the HMO early the next month.")
    if not any(((providers or {}).get(p) or {}).get("rate") for p in {r["hmo_provider"] for r in hm}):
        st.caption("Add each HMO's rate in HMO settings to see the amount to claim.")
    visits = month_visits(supabase, gym_id, hm, providers, pick)
    saved = {(c["provider"], str(c["month"])[:10]): c for c in claims}
    for f in claim_figures(hm, providers, visits, pick):
        c = saved.get((f["provider"], pick.isoformat()))
        hp = providers.get(f["provider"]) or {}
        with st.container(border=True):
            head = f"**{f['provider']}** · {_money(f['amount'])}"
            if c:
                head += f" · {CLAIM_STATUS.get(c['status'], c['status'])}"
            st.markdown(head)
            basis = (f"{f['claimable']} claimable visit{'s' if f['claimable'] != 1 else ''} × {_money(f['rate'])}"
                     if f["model"] == "per_visit" else
                     f"{f['members']} member{'s' if f['members'] != 1 else ''} on cover × {_money(f['rate'])}")
            notes = [basis if f["rate"] else "No rate set in HMO settings"]
            if f["over"]:
                notes.append(f"{f['over']} visit{'s' if f['over'] != 1 else ''} over the weekly limit left out")
            if f["no_code"]:
                notes.append(f"{f['no_code']} visit{'s' if f['no_code'] != 1 else ''} without the HMO's code left out")
            if not c:
                left = (f["send_by"] - today).days
                notes.append(f"send by {f['send_by']:%d %b}" + (" (late)" if left < 0 else ""))
            st.caption(" · ".join(notes))
            part = visits[visits["HMO"] == f["provider"]] if len(visits) else visits
            claim_df = part[part["Claimable"]][["Name", "HMO ID", "Plan", "Employer", "Date", "Code"]] \
                if len(part) else pd.DataFrame(columns=["Name", "HMO ID", "Plan", "Employer", "Date", "Code"])
            fname = f"claim-{re.sub(r'[^A-Za-z0-9]+', '-', f['provider'])}-{pick:%Y-%m}.csv"
            key = re.sub(r"[^A-Za-z0-9]+", "_", f["provider"]) + f"_{pick:%Y%m}"
            b1, b2, b3 = st.columns(3)
            import gympulse_reports as rp
            with b1:
                rp.download_link("Download claim (CSV)", claim_df.to_csv(index=False), fname, "text/csv", f"hmo_cl_{key}")
            if not c:
                import gympulse_campaigns as gcamp
                email = gw._text(hp.get("claims_email"))
                if "@" in email and gcamp.ready() and len(claim_df):
                    if b2.button("Email claim to HMO", key=f"hmo_em_{key}", icon=":material/mail:",
                                 use_container_width=True):
                        biz, owner = _biz()
                        body = (f"Dear {f['provider']} claims team,\n\nPlease find attached {biz}'s gym claim for "
                                f"{pick:%B %Y}: {f['claimable']} visits by {f['members']} enrollees, "
                                f"{_money(f['amount'])} in total. Each visit is listed with the enrollee's name, HMO ID "
                                "and date.\n\nKind regards,\n" + "\n".join(x for x in (owner, biz) if x))
                        try:
                            gcamp.email_letter(email, f"{biz}: gym claim for {pick:%B %Y}", body,
                                               attachments=[(fname, claim_df.to_csv(index=False).encode())])
                            _save_claim(supabase, gym_id, f, pick, {"status": "sent", "sent_on": today.isoformat()},
                                        f"Claim emailed to {email} and marked sent.")
                        except Exception as error:
                            st.error(f"Could not send: {error}")
                if b3.button("Mark sent", key=f"hmo_sent_{key}", icon=":material/send:", use_container_width=True):
                    _save_claim(supabase, gym_id, f, pick, {"status": "sent", "sent_on": today.isoformat()},
                                f"{f['provider']} claim for {pick:%B %Y} marked sent.")
            else:
                sent = _date(c.get("sent_on"))
                if sent and c["status"] != "paid":
                    days = (today - sent).days
                    (st.warning if days > LATE_DAYS else st.caption)(
                        f"Sent {sent:%d %b %Y}, {days} day{'s' if days != 1 else ''} ago"
                        + (". Follow up with the HMO." if days > LATE_DAYS else "."))
                with st.popover("Record payment or query", icon=":material/payments:", use_container_width=True):
                    with st.form(f"hmo_pay_{key}"):
                        paid = st.number_input("Amount received (₦)", 0.0, value=float(c.get("amount_paid") or c["amount"]),
                                               step=1000.0)
                        on = st.date_input("Date received", value=_date(c.get("paid_on")) or today, format="DD/MM/YYYY")
                        note = st.text_input("Note (optional)", value=gw._text(c.get("note")),
                                             placeholder="e.g. 3 visits queried: no code")
                        s1, s2 = st.columns(2)
                        if s1.form_submit_button("Save payment", type="primary"):
                            status = "paid" if paid >= float(c["amount"] or 0) else "part_paid"
                            _update_claim(supabase, c["id"], {"amount_paid": paid, "paid_on": on.isoformat(),
                                                               "status": status, "note": note.strip() or None})
                        if s2.form_submit_button("HMO queried it"):
                            _update_claim(supabase, c["id"], {"status": "queried", "note": note.strip() or None})
    unpaid = [c for c in claims if c.get("status") != "paid"]
    if unpaid:
        st.markdown("**Claims not yet fully paid**")
        gw.table([{"HMO": c["provider"], "Month": f"{_date(c['month']):%b %Y}", "Claimed": _money(c["amount"]),
                   "Received": _money(c.get("amount_paid") or 0), "Status": CLAIM_STATUS.get(c["status"], c["status"]),
                   "Sent": f"{_date(c['sent_on']):%d %b}" if _date(c.get("sent_on")) else "",
                   "Days waiting": (today - _date(c["sent_on"])).days if _date(c.get("sent_on")) else ""}
                  for c in unpaid], pills=("Status",))


def _biz():
    p = st.session_state.get("user_profile") or {}
    return gw._text(p.get("business_name"), "our gym"), gw._text(p.get("full_name"), "")


def _save_claim(supabase, gym_id, f, month, extra, flash):
    row = {"gym_id": gym_id, "provider": f["provider"], "month": month.isoformat(), "visits": f["claimable"],
           "members": f["members"], "amount": f["amount"], **extra}
    try:
        supabase.table("hmo_claims").upsert(row, on_conflict="gym_id,provider,month").execute()
        st.session_state["grow_flash"] = flash
        st.rerun()
    except Exception as error:
        st.error(f"Could not save: {error}")


def _update_claim(supabase, claim_id, fields):
    try:
        supabase.table("hmo_claims").update(fields).eq("id", claim_id).execute()
        st.session_state["grow_flash"] = "Claim updated."
        st.rerun()
    except Exception as error:
        st.error(f"Could not save: {error}")


# ------------------------------------------------------------------ visits report
def _report(supabase, gym_id, hm, providers):
    today = gw.today_local()
    pick = st.selectbox("Month", _months(today), format_func=lambda d: f"{d:%B %Y}", key="hmo_month")
    if not hm:
        st.caption("No HMO visits yet.")
        return
    v = month_visits(supabase, gym_id, hm, providers, pick)
    if v.empty:
        st.caption(f"No HMO visits in {pick:%B %Y}.")
        return
    rows = []
    for mid, grp in v.groupby("member_id"):
        r = grp.iloc[0]
        rows.append({"HMO": r["HMO"], "Name": r["Name"], "HMO ID": r["HMO ID"], "Plan": r["Plan"],
                     "Employer": r["Employer"], "Visits": len(grp), "Over limit": int(grp["Over limit"].sum()),
                     "No code": int(grp["No code"].sum()),
                     "Dates": ", ".join(f"{d:%d}" for d in sorted(grp["Date"]))})
    df = pd.DataFrame(rows).sort_values(["HMO", "Name"])
    summary = df.groupby("HMO").agg(Members=("Name", "count"), Visits=("Visits", "sum"),
                                    **{"Over limit": ("Over limit", "sum"), "No code": ("No code", "sum")}).reset_index()
    gw.table(summary.to_dict("records"), caption=f"HMO visits in {pick:%B %Y} (one per member per day). "
             "Visits over the member's weekly sessions, or without a code the HMO needs, may not be paid.")
    import gympulse_reports as rp
    rp.download_link(f"Download all ({len(df)} members)", df.to_csv(index=False), f"hmo-visits-{pick:%Y-%m}.csv",
                     "text/csv", "hmo_dl_all")
    with st.expander("See every member"):
        gw.table(df.to_dict("records"), max_height=420)


# ------------------------------------------------------------------ HMO settings
def _settings(supabase, gym_id, hm, providers):
    if providers is None:
        st.info(SQL37_HINT)
        return
    names = sorted({r["hmo_provider"] for r in hm} | set(providers))
    st.caption("Set how each HMO pays you and its rules for gym visits. You'll find these in your agreement with "
               "the HMO, or ask their provider relations team.")
    if not names:
        st.caption("Import an HMO list or add an HMO member first.")
        return
    for name in names:
        hp = providers.get(name) or {}
        k = re.sub(r"[^A-Za-z0-9]+", "_", name)
        with st.expander(f"{name}" + ("" if hp else " · not set up yet"), expanded=not hp):
            with st.form(f"hmo_set_{k}"):
                c1, c2 = st.columns(2)
                model = c1.selectbox("They pay you", list(PAY_MODELS), format_func=PAY_MODELS.get,
                                     index=list(PAY_MODELS).index(hp.get("pay_model") or "per_visit"))
                rate = c2.number_input("Rate (₦)", 0.0, value=float(hp.get("rate") or 0), step=500.0,
                                       help="Per visit, or per member each month, as agreed with the HMO.")
                c3, c4 = st.columns(2)
                lim = c3.number_input("Usual gym sessions per week (0 = no limit)", 0, 7,
                                      int(hp.get("weekly_limit") or 0),
                                      help="Most plans allow 1, 2 or 3 a week. A member's own plan limit, if set, "
                                           "comes first.")
                days = c4.number_input("Send claims within (days after the month)", 1, 120,
                                       int(hp.get("claim_days") or 30))
                needs = st.checkbox("They need a code for each visit (from the HMO's app or SMS)",
                                    value=bool(hp.get("needs_code")))
                email = st.text_input("Claims email (optional)", value=gw._text(hp.get("claims_email")),
                                      placeholder="e.g. claims@hmo.com")
                if st.form_submit_button("Save", type="primary"):
                    row = {"gym_id": gym_id, "name": name, "pay_model": model, "rate": rate or None,
                           "weekly_limit": int(lim) or None, "claim_days": int(days), "needs_code": bool(needs),
                           "claims_email": email.strip() or None}
                    try:
                        supabase.table("hmo_providers").upsert(row, on_conflict="gym_id,name").execute()
                        st.session_state["grow_flash"] = f"{name} settings saved."
                        st.rerun()
                    except Exception as error:
                        st.error(f"Could not save: {error}")


# ------------------------------------------------------------------ import and add
def _guess(columns):
    norm = {c: re.sub(r"[^a-z0-9 ]+", " ", str(c).lower()).strip() for c in columns}
    norm = {c: re.sub(r"\s+", " ", v) for c, v in norm.items()}
    out, used = {}, set()
    for k, names in COLS.items():
        hit = next((c for c in columns if norm[c] in names and c not in used), None)
        out[k] = hit
        if hit:
            used.add(hit)
    return out


def _import(supabase, gym_id, hm):
    st.markdown("**Import the HMO's member list**")
    st.caption("A CSV or Excel file from the HMO: name, phone or email, HMO ID, and (if you have them) the HMO "
               "name, plan, gym sessions per week, employer and cover end date. Existing members are matched by "
               "HMO ID, phone or email.")
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
                     "plan": get("plan"), "limit": _limit_from(get("limit")),
                     "valid": None if pd.isna(valid) else valid.date()})
    rows = [r for r in rows if r["provider"]]
    if not rows:
        st.warning("Choose which HMO this list is from.")
        return
    new = sum(1 for r in rows if not r["id"])
    import gympulse_billing as gbill
    ok, why = gbill.can_add_members(supabase, gym_id, adding=new) if new else (True, "")
    if not ok:
        st.error(why + f" This list has {new:,} new member{'s' if new != 1 else ''}. Members already in "
                 "GymPulse can still be marked as HMO members: remove the new ones from the file, or upgrade.")
        return
    found = [lbl for k, lbl in (("plan", "plan"), ("limit", "sessions per week"), ("valid", "cover end date"))
             if cols.get(k)]
    st.write(f"**{len(rows)}** HMO members found: **{len(rows) - new}** already in GymPulse, **{new}** new."
             + (f" Also read: {', '.join(found)}." if found else ""))
    if st.button(f"Import {len(rows)} HMO members", type="primary", icon=":material/upload:", key="hmo_go",
                 use_container_width=True):
        done, failed = save_rows(supabase, gym_id, rows)
        st.session_state["grow_flash"] = (f"{done} HMO member{'s' if done != 1 else ''} saved."
                                          + (f" {failed} couldn't be saved." if failed else "")
                                          + " They can check in with the HMO QR code now.")
        st.session_state.pop("hmo_up", None)
        st.rerun()


def _without_phase37(fields):
    return {k: v for k, v in fields.items() if k not in ("hmo_plan", "hmo_weekly_limit")}


def save_rows(supabase, gym_id, rows):
    import gympulse_gymmaster as ggm
    now = pd.Timestamp.now(tz="UTC").isoformat()
    today = gw.today_local()
    done = failed = 0
    bar = st.progress(0.0, text="Saving HMO members…")
    for i, r in enumerate(rows, 1):
        fields = {"hmo_provider": r["provider"][:80], "hmo_id": (r["hmo_id"] or None),
                  "hmo_employer": (r["employer"] or None)}
        if r.get("plan"):
            fields["hmo_plan"] = r["plan"][:60]
        if r.get("limit"):
            fields["hmo_weekly_limit"] = int(r["limit"])
        if r["valid"]:
            fields["hmo_valid_until"] = r["valid"].isoformat()
        try:
            if r["id"]:
                try:
                    supabase.table("members").update(fields).eq("id", r["id"]).execute()
                except Exception:
                    supabase.table("members").update(_without_phase37(fields)).eq("id", r["id"]).execute()
            else:
                data = {"gym_id": gym_id, "full_name": r["name"][:120], "phone": r["phone"] or None,
                        "email": r["email"] or None, **fields}
                if r["valid"]:
                    data["membership_end"] = r["valid"].isoformat()
                mid, _ = ggm._insert_member(supabase, data)
                if not mid and data != _without_phase37(data):
                    mid, _ = ggm._insert_member(supabase, _without_phase37(data))
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


def _add_one(supabase, gym_id, plans_ready=True):
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
        plan = lim = None
        if plans_ready:
            c6, c7 = st.columns(2)
            plan = c6.text_input("Plan (optional)", placeholder="e.g. Emerald, Diamond, HyFit Platinum")
            lim = c7.number_input("Gym sessions per week (0 = the HMO's usual)", 0, 7, 0)
        if st.form_submit_button("Save", type="primary"):
            provider = other.strip() if prov == "Other" else prov
            if not mid or not provider:
                st.error("Choose the member and their HMO.")
            else:
                fields = {"hmo_provider": provider, "hmo_id": hid.strip() or None, "hmo_employer": emp.strip() or None,
                          "hmo_valid_until": valid.isoformat() if valid else None}
                if plans_ready:
                    fields.update({"hmo_plan": (plan or "").strip() or None, "hmo_weekly_limit": int(lim) or None})
                supabase.table("members").update(fields).eq("id", mid).execute()
                gw.bump_data_version()
                st.session_state["grow_flash"] = f"{names[mid]} is now an HMO member ({provider})."
                st.rerun()


def _members_list(hm, ending, providers, week):
    if not hm:
        st.caption("No HMO members yet. Import the HMO's list or add one member.")
        return
    if ending:
        st.warning(f"{len(ending)} HMO cover{'s end' if len(ending) != 1 else ' ends'} in the next 30 days: "
                   + ", ".join(r["full_name"] for r in ending[:6]) + ("…" if len(ending) > 6 else ""))
    gw.table([{"Name": r["full_name"], "HMO": r["hmo_provider"], "Plan": r.get("hmo_plan") or "",
               "HMO ID": r.get("hmo_id") or "",
               "Sessions/week": week_limit(r, providers) or "No limit",
               "This week": int(week.get(r["id"], 0)),
               "Employer": r.get("hmo_employer") or "", "Cover ends": str(r.get("hmo_valid_until") or "")[:10]}
              for r in sorted(hm, key=lambda r: (r["hmo_provider"], r["full_name"]))], max_height=480)
