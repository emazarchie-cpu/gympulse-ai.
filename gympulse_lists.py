"""GymPulse AI · Member lists: pick who you want, choose the columns, then download or contact them.

Owner → Member lists. Filters a gym owner actually uses ("expired in the last 30 days", "owes money",
"birthday this month", "hasn't been in for 2 weeks"), the columns they want, a CSV download, and three ways to
act on the list: a WhatsApp message for each person, calls for the team in the Action Centre, or copy numbers.
"""
from datetime import timedelta
from urllib.parse import quote

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

COLUMNS = ["Name", "Phone", "Email", "Member code", "Plan", "Plan ends", "Status", "Last visit",
           "Visits (30 days)", "Risk", "Owes", "Joined", "Birthday"]
DEFAULT_COLS = ["Name", "Phone", "Plan ends", "Status", "Last visit", "Owes"]
STATUSES = ["Active", "Ends within 7 days", "Expired", "No plan"]


def _num(x, default=0):
    try:
        v = float(x)
        return default if pd.isna(v) else v
    except (TypeError, ValueError):
        return default


def build_table(supabase, gym_id, assess_fn):
    """One row per current member with everything the filters and columns need."""
    members, _ = gw.fetch_members(supabase, gym_id, archived=False, include_photo=False)
    if members.empty:
        return pd.DataFrame()
    df = members.copy()
    try:
        roster, _missing = gw.load_roster(supabase, gym_id, assess_fn, with_photos=False)
    except Exception:
        roster = pd.DataFrame()
    if isinstance(roster, pd.DataFrame) and not roster.empty:
        key = "member_id" if "member_id" in roster.columns else "id"
        keep = [c for c in ("risk_category", "days_since_last_visit", "visits_last_30_days", "membership_type")
                if c in roster.columns]
        df = df.merge(roster[[key] + keep].rename(columns={key: "id"}).drop_duplicates("id"), on="id", how="left")
    try:
        extra = pd.DataFrame(gw.fetch_all(supabase.table("members").select("id, balance_owed")
                                          .eq("gym_id", gym_id).order("id")))
        if not extra.empty:
            df = df.merge(extra, on="id", how="left")
    except Exception:
        pass
    for c in ("risk_category", "days_since_last_visit", "visits_last_30_days", "membership_type", "balance_owed",
              "date_of_birth"):
        if c not in df.columns:
            df[c] = None
    today = pd.Timestamp(gw.today_local())
    end = pd.to_datetime(df["membership_end"], errors="coerce")
    left = (end - today).dt.days

    def status(i):
        if pd.isna(end.iloc[i]):
            return "No plan"
        if left.iloc[i] < 0:
            return "Expired"
        return "Ends within 7 days" if left.iloc[i] <= 7 else "Active"
    df["_status"] = [status(i) for i in range(len(df))]
    df["_left"] = left
    df["_away"] = pd.to_numeric(df["days_since_last_visit"], errors="coerce")
    df["_owes"] = pd.to_numeric(df["balance_owed"], errors="coerce").fillna(0)
    df["_dob"] = pd.to_datetime(df["date_of_birth"], errors="coerce")
    df["_joined"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True).dt.tz_convert(gw.APP_TZ) \
        .dt.tz_localize(None)
    return df


def _row(r, today):
    away = r["_away"]
    last = "" if pd.isna(away) else f"{(today - pd.Timedelta(days=int(away))):%d %b %Y}"
    end = pd.to_datetime(r.get("membership_end"), errors="coerce")
    return {"Name": gw._text(r.get("full_name"), ""), "Phone": gw._text(r.get("phone"), ""),
            "Email": gw._text(r.get("email"), ""), "Member code": gw.member_code(r["id"]),
            "Plan": gw._text(r.get("membership_type"), ""), "Plan ends": "" if pd.isna(end) else f"{end:%d %b %Y}",
            "Status": r["_status"], "Last visit": last,
            "Visits (30 days)": "" if pd.isna(r.get("visits_last_30_days")) else int(_num(r.get("visits_last_30_days"))),
            "Risk": gw._text(r.get("risk_category"), ""),
            "Owes": f"₦{r['_owes']:,.0f}" if r["_owes"] > 0 else "",
            "Joined": "" if pd.isna(r["_joined"]) else f"{r['_joined']:%d %b %Y}",
            "Birthday": "" if pd.isna(r["_dob"]) else f"{r['_dob']:%d %b}"}


def render_lists(supabase, gym_id, assess_fn):
    df = build_table(supabase, gym_id, assess_fn)
    if df.empty:
        st.info("Add members first, then build lists of them here.")
        return
    st.caption("Choose who you want, then download the list or contact everyone on it.")
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        status = c1.multiselect("Membership", STATUSES, default=[], placeholder="Any")
        away = c2.number_input("Not in for at least (days)", min_value=0, max_value=365, value=0, step=7,
                               help="0 means any.")
        ends = c3.number_input("Plan ends within (days)", min_value=0, max_value=365, value=0, step=7,
                               help="0 means any. Only members whose plan hasn't ended yet.")
        c4, c5, c6 = st.columns(3)
        risk = c4.multiselect("Risk", ["High", "Medium", "Low"], default=[], placeholder="Any")
        joined = c5.number_input("Joined in the last (days)", min_value=0, max_value=3650, value=0, step=30,
                                 help="0 means any.")
        c6.write("")
        owes = c6.checkbox("Owes money")
        bday = c6.checkbox("Birthday this month")
    today = pd.Timestamp(gw.today_local())
    f = df
    if status:
        f = f[f["_status"].isin(status)]
    if away:
        f = f[f["_away"] >= away]
    if ends:
        f = f[(f["_left"] >= 0) & (f["_left"] <= ends)]
    if risk:
        f = f[f["risk_category"].astype(str).isin(risk)]
    if joined:
        f = f[f["_joined"] >= today - pd.Timedelta(days=joined)]
    if owes:
        f = f[f["_owes"] > 0]
    if bday:
        f = f[f["_dob"].dt.month == today.month]
    cols = st.multiselect("Columns", COLUMNS, default=DEFAULT_COLS)
    rows = [_row(r, today) for _, r in f.sort_values("full_name").iterrows()]
    st.markdown(f"**{len(rows)} member{'s' if len(rows) != 1 else ''}**")
    if not rows:
        st.caption("Nobody matches. Loosen a filter.")
        return
    gw.table([{c: r[c] for c in cols or ["Name"]} for r in rows[:300]])
    if len(rows) > 300:
        st.caption(f"Showing the first 300. The download has all {len(rows)}.")
    csv = pd.DataFrame([{c: r[c] for c in cols or ["Name"]} for r in rows]).to_csv(index=False)
    st.download_button("Download the list (CSV, opens in Excel)", csv, "GymPulse member list.csv", "text/csv",
                       key="lists_dl")

    st.markdown("**Contact everyone on the list**")
    how = st.segmented_control("How", ["WhatsApp each", "Calls for my team", "Copy numbers"],
                               default="WhatsApp each", key="lists_how", label_visibility="collapsed")
    ids = list(f.sort_values("full_name")["id"])
    if how == "WhatsApp each":
        gym = gw._text((st.session_state.get("user_profile") or {}).get("business_name"), "the gym")
        msg = st.text_area("Message ({name} becomes each person's first name)",
                           value=f"Hi {{name}}, it's {gym}. ", key="lists_msg", height=90)
        st.caption("Each button opens WhatsApp with the message ready. You press send.")
        shown = 0
        for r, (_, m) in zip(rows, f.sort_values("full_name").iterrows()):
            d = gw.whatsapp_digits(m.get("phone"))
            if not d or len(d) < 10:
                continue
            first = r["Name"].split(" ")[0]
            st.link_button(f"WhatsApp {r['Name']}", f"https://wa.me/{d}?text={quote(msg.replace('{name}', first))}")
            shown += 1
            if shown >= 60:
                st.caption("Showing the first 60. Narrow the list to see the rest.")
                break
        if not shown:
            st.caption("Nobody on this list has a phone number saved.")
    elif how == "Calls for my team":
        note = st.text_input("Why they're being called", placeholder="e.g. Plan ended last month: offer to renew",
                             key="lists_note")
        if st.button(f"Add {len(ids)} call{'s' if len(ids) != 1 else ''} to the Action Centre", type="primary",
                     key="lists_calls", disabled=not ids or len(ids) > 200):
            made = 0
            for mid in ids:
                try:
                    gw._create_action(supabase, gym_id, mid, "Personal call", 0, note=note.strip() or "From a member list")
                    made += 1
                except Exception:
                    pass
            gw.bump_data_version(gym_id)
            st.success(f"Added {made} call{'s' if made != 1 else ''} to the Action Centre.")
        if len(ids) > 200:
            st.caption("That's a lot of calls. Narrow the list to 200 or fewer.")
    else:
        nums = [r["Phone"] for r in rows if r["Phone"]]
        st.code(", ".join(nums) or "No phone numbers on this list.", language=None)
