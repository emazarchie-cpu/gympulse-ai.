"""GymPulse AI · Branches: one owner login, several gyms (a chain such as Lekki, Ikeja and Abuja).

Each branch is its own gym in GymPulse AI (its own members, check-ins, staff, plan and member limit), owned by
the same login. The owner switches branch at the top of the app, and the Branches page (HQ) compares them all
and adds new ones. Staff and trainers are added per branch, so a branch manager only ever sees their branch.
Settings on the owner's profile (branding, automatic messages, house rules, member app on/off, side by side)
apply to every branch.

Database: nothing new; branches are rows in gyms with the same owner_id (RLS already lets the owner see each).
"""
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

MAX_BRANCHES = 50


def load(supabase, owner_id):
    """The owner's gyms, oldest first."""
    try:
        return (supabase.table("gyms").select("*").eq("owner_id", owner_id).order("created_at")
                .limit(MAX_BRANCHES).execute().data or [])
    except Exception:
        return []


def pick(rows):
    """The branch to work in: the one chosen this session, else the first (oldest)."""
    want = st.session_state.get("branch_id")
    return next((g for g in rows if str(g["id"]) == str(want)), rows[0])


def name_of(g):
    return gw._text(g.get("branch_name")) or gw._text(g.get("business_name"), "Branch")


def render_switcher(branches, current_id):
    """A branch picker at the top of every page, for owners with more than one branch."""
    if len(branches) < 2:
        return
    ids = [str(g["id"]) for g in branches]
    names = {str(g["id"]): name_of(g) for g in branches}
    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    pick_id = c1.selectbox("Branch", ids, index=ids.index(str(current_id)) if str(current_id) in ids else 0,
                           format_func=names.get, key="branch_pick", label_visibility="collapsed")
    if c2.button("All branches", key="branch_hq", icon=":material/domain:", use_container_width=True):
        st.session_state["navigate_to"] = "Branches"
        st.rerun()
    if pick_id != str(current_id) and st.session_state.get("branch_id") != pick_id:   # once, never a loop
        st.session_state["branch_id"] = pick_id
        st.session_state.pop("_cache", None)
        st.rerun()


# ------------------------------------------------------------------ HQ: every branch side by side
def _count(supabase, table, gym_id, **filters):
    try:
        q = supabase.table(table).select("id", count="exact").eq("gym_id", gym_id)
        for k, v in filters.items():
            op, val = v
            q = getattr(q, op)(k, val)
        res = q.limit(1).execute()
        return int(res.count or 0)
    except Exception:
        return None


def branch_stats(supabase, g, assess_fn):
    gid = g["id"]
    today = gw.today_local()
    month_start = datetime.combine(today.replace(day=1), datetime.min.time()).replace(tzinfo=gw.APP_TZ).isoformat()
    since30 = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    out = {"Branch": name_of(g)}
    try:
        roster = gw.load_roster(supabase, gid, assess_fn, with_photos=False)
        roster = roster[0] if isinstance(roster, tuple) else roster
    except Exception:
        roster = pd.DataFrame()
    if roster is not None and len(roster):
        out["Members"] = int(len(roster))
        out["At risk"] = int((roster.get("risk_category") == "High").sum()) if "risk_category" in roster else None
        due = pd.to_numeric(roster.get("renewal_due_days"), errors="coerce") if "renewal_due_days" in roster else None
        out["Renewing in 14 days"] = int(((due >= 0) & (due <= 14)).sum()) if due is not None else None
    else:
        out["Members"] = _count(supabase, "members", gid, archived=("eq", False)) or 0
        out["At risk"], out["Renewing in 14 days"] = None, None
    out["Visits this month"] = _count(supabase, "checkins", gid, checked_in_at=("gte", month_start))
    out["Won back (30 days)"] = _count(supabase, "retention_actions", gid, status=("eq", "Done"),
                                       outcome=("eq", "Retained"), completed_at=("gte", since30))
    try:
        rows = gw.fetch_all(supabase.table("payments").select("amount").eq("gym_id", gid)
                            .gte("paid_on", (today - timedelta(days=30)).isoformat()))
        out["Collected (30 days)"] = sum(float(r.get("amount") or 0) for r in rows)
    except Exception:
        out["Collected (30 days)"] = None
    return out


CARD_CSS = """
.br-card { border: 1px solid var(--gp-line); border-radius: 18px; padding: 16px 18px 14px; margin: 0 0 4px;
    background: linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01)), var(--gp-s1); }
.br-card.cur { border-color: rgba(183,243,74,0.45); }
.br-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 12px; }
.br-name { font-family: var(--gp-display); font-size: 19px; font-weight: 700; color: var(--gp-text);
    min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.br-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.br-stat { border-radius: 12px; padding: 10px 12px; background: var(--gp-s2); min-width: 0; }
.br-stat span { display: block; font-size: 11.5px; color: var(--gp-muted); line-height: 1.3; }
.br-stat b { display: block; font-family: var(--gp-display); font-size: 20px; color: var(--gp-text); margin-top: 2px;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.br-stat.red b { color: #FF8A7A; } .br-stat.amber b { color: #FFC44D; } .br-stat.lime b { color: #B7F34A; }
@media (max-width: 640px) { .br-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); } .br-stat b { font-size: 18px; } }
"""


def _num(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) else v


def _branch_card(g, row, current):
    """One branch: its name, and its numbers in tiles that wrap on a phone."""
    is_cur = str(g["id"]) == current
    members, risk = _num(row.get("Members")), _num(row.get("At risk"))
    renew, visits = _num(row.get("Renewing in 14 days")), _num(row.get("Visits this month"))
    won, money = _num(row.get("Won back (30 days)")), _num(row.get("Collected (30 days)"))
    share = f" · {risk / members:.0%}" if members and risk else ""

    def tile(label, value, tone=""):
        return f'<div class="br-stat {tone}"><span>{label}</span><b>{value}</b></div>'

    fmt = lambda v: "–" if v is None else f"{int(v):,}"
    tiles = (tile("Members", fmt(members))
             + tile("At risk" + share, fmt(risk), "red" if risk else "")
             + tile("Renewing in 14 days", fmt(renew), "amber" if renew else "")
             + tile("Visits this month", fmt(visits))
             + tile("Won back · 30 days", fmt(won), "lime" if won else "")
             + tile("Collected · 30 days", "–" if money is None else f"₦{money:,.0f}"))
    pill = '<span class="gp-pill gp-pill-lime">Working in it</span>' if is_cur else ""
    with st.container(key=f"br_card_{g['id']}"):
        gw._md(f'<div class="br-card{" cur" if is_cur else ""}"><div class="br-head">'
               f'<div class="br-name">{gw._esc(name_of(g))}</div>{pill}</div>'
               f'<div class="br-stats">{tiles}</div></div>')
        if not is_cur and st.button(f"Work in {name_of(g)}", key=f"br_go_{g['id']}", icon=":material/arrow_forward:",
                                    type="tertiary"):
            st.session_state["branch_id"] = str(g["id"])
            st.session_state.pop("branch_pick", None)      # so the picker at the top follows, not undoes, the switch
            st.session_state.pop("_cache", None)
            st.session_state["navigate_to"] = "Dashboard"
            st.rerun()


def render_hq(supabase, owner_id, branches, assess_fn):
    gw.page_header("Branches", "Every branch side by side, and add new ones.", "Your company")
    flash = st.session_state.pop("branch_flash", None)
    if flash:
        st.success(flash)
    if st.session_state.get("role") == "staff":
        st.info("Only the owner can see all branches.")
        return
    stats = [branch_stats(supabase, g, assess_fn) for g in branches]
    df = pd.DataFrame(stats)
    totals = {k: df[k].dropna().sum() for k in df.columns if k != "Branch" and pd.api.types.is_numeric_dtype(df[k])}
    gw.kpi_row([("Branches", str(len(branches)), "cyan", ""),
                ("Members", f"{int(totals.get('Members', 0)):,}", "lime", "across all branches"),
                ("At risk", f"{int(totals.get('At risk', 0)):,}", "red" if totals.get("At risk") else "grey", "right now"),
                ("Collected", f"₦{totals.get('Collected (30 days)', 0):,.0f}", "amber", "last 30 days")])
    gw._md(f"<style>{CARD_CSS}</style>")
    current = str(st.session_state.get("branch_id") or (branches[0]["id"] if branches else ""))
    for g, row in zip(branches, stats):
        _branch_card(g, row, current)
    if len(branches) > 1:
        st.caption("Staff and trainers are added per branch (Owner → Team), so a branch manager only sees their "
                   "own branch.")
    with st.expander("Add a branch", icon=":material/add_business:", expanded=len(branches) < 2):
        st.caption("A branch is a separate gym with its own members, check-ins, staff and plan, under your login. "
                   "Each new branch starts with the 30-day free trial.")
        with st.form("branch_new", clear_on_submit=True):
            name = st.text_input("Branch name", placeholder="e.g. i-Fitness Ikeja")
            go = st.form_submit_button("Add branch", type="primary", use_container_width=True)
        if go:
            if len(name.strip()) < 2:
                st.error("Type the branch name.")
            elif len(branches) >= MAX_BRANCHES:
                st.error(f"You can have up to {MAX_BRANCHES} branches. Contact us for more.")
            else:
                try:
                    row = supabase.table("gyms").insert({"owner_id": owner_id, "business_name": name.strip()[:80]}) \
                        .execute().data
                    gw.bump_data_version()
                    if row:
                        st.session_state["branch_id"] = str(row[0]["id"])
                    st.session_state["branch_flash"] = (f"{name.strip()} added. You're now working in it: import its "
                                                        "members from Member Management.")
                    st.session_state.pop("_cache", None)
                    st.rerun()
                except Exception as error:
                    if type(error).__name__ in ("RerunException", "StopException"):
                        raise
                    st.error(f"Could not add the branch: {error}")
    if len(branches) > 1:
        with st.expander("Rename a branch", icon=":material/edit:"):
            names = {str(g["id"]): name_of(g) for g in branches}
            with st.form("branch_rename"):
                pid = st.selectbox("Branch", list(names), format_func=names.get)
                new = st.text_input("New name")
                ok = st.form_submit_button("Rename", type="primary")
            if ok and len(new.strip()) >= 2:
                try:
                    supabase.table("gyms").update({"business_name": new.strip()[:80]}).eq("id", pid) \
                        .eq("owner_id", owner_id).execute()
                    gw.bump_data_version()
                    st.session_state.pop("_cache", None)
                    st.session_state["branch_flash"] = f"Renamed to {new.strip()}."
                    st.rerun()
                except Exception as error:
                    if type(error).__name__ in ("RerunException", "StopException"):
                        raise
                    st.error(f"Could not rename: {error}")
