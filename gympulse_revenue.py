"""Phase 3: connect retention work to revenue.

Every renewal or payment is one row in `payments`. A payment can be credited to
at most one retention play (and each play to at most one payment), so the same
money is never counted twice. A member counts as "retained by a play" only when
a payment confirms it, never because a message was sent.

Everything here degrades gracefully: before sql/phase3_revenue.sql is run the
renewal is still saved on the member, and reports fall back to recorded
outcomes, clearly labelled.
"""
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

ATTRIBUTION_WINDOW_DAYS = 45      # a play gets credit if the member was worked within this window
PAYMENT_KINDS = {"new": "New member", "renewal": "Renewal", "recovered": "Recovered (was lapsed)",
                 "other": "Other payment"}
PAYMENT_METHODS = ["Cash", "Bank transfer", "Card", "POS", "Mobile money", "Other"]


# ------------------------------------------------------------------ storage
def _fetch_payments_uncached(supabase, gym_id, days=400):
    since = (date.today() - timedelta(days=days)).isoformat()
    try:
        rows = gw.fetch_all(supabase.table("payments").select("*").eq("gym_id", gym_id)
                            .gte("paid_on", since).order("paid_on", desc=True).order("id"))
    except Exception:
        return None                        # table not created yet
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["id", "member_id", "amount", "paid_on", "kind",
                                     "action_id", "plan", "covers_until", "method", "note"])
    if "created_at" in df.columns:
        df = df.sort_values(["paid_on", "created_at"], ascending=False).reset_index(drop=True)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    df["paid_on"] = pd.to_datetime(df["paid_on"], errors="coerce").dt.date
    for col in ("action_id", "kind", "plan", "method", "note", "covers_until"):
        if col not in df.columns:
            df[col] = None
    return df


def load_payments(supabase, gym_id):
    """Payments from the last ~13 months, or None if the table doesn't exist yet."""
    return gw._cached(("payments", gym_id), lambda: _fetch_payments_uncached(supabase, gym_id))


def payments_ready(supabase, gym_id):
    return load_payments(supabase, gym_id) is not None


# ------------------------------------------------------------------ attribution
def _credited_action_ids(supabase, gym_id):
    p = load_payments(supabase, gym_id)
    if p is None or p.empty:
        return set()
    return set(p["action_id"].dropna().astype(str))


def find_creditable_play(supabase, gym_id, member_id, paid_on):
    """The play that earned this payment: the member's most recent play that was
    worked (started or contacted) within the window before the payment, and not
    already credited to another payment. Cancelled plays never get credit."""
    try:
        rows = (supabase.table("retention_actions").select("*").eq("member_id", member_id)
                .order("created_at", desc=True).limit(20).execute().data or [])
    except Exception:
        return None
    credited = _credited_action_ids(supabase, gym_id)
    history = payments_ready(supabase, gym_id)
    start = pd.Timestamp(paid_on) - pd.Timedelta(days=ATTRIBUTION_WINDOW_DAYS)
    # A play can only earn the renewal it led to: it must have been worked after
    # this member's previous payment. A second payment straight after the first
    # therefore gets no credit, even if another play happens to be open.
    previous = _last_payment_time(supabase, gym_id, member_id)
    if previous is not None:
        start = max(start, previous)
    # Prefer plays where the member was actually reached, most recent first
    rows = sorted(rows, key=lambda r: (not gw._blank(r.get("contacted_at")),
                                       str(r.get("contacted_at") or r.get("created_at") or "")),
                  reverse=True)
    for r in rows:
        if str(r.get("id")) in credited or r.get("outcome") == "Cancelled":
            continue
        if not history and r.get("status") == "Done":
            continue          # without a payment history we can't tell if it was credited before
        worked = r.get("contacted_at") or r.get("created_at")
        when = pd.to_datetime(worked, errors="coerce", utc=True, format="ISO8601")
        if pd.isna(when):
            continue
        when = when.tz_localize(None)
        if start <= when <= pd.Timestamp(paid_on) + pd.Timedelta(days=1):
            return r
    return None


def _last_payment_time(supabase, gym_id, member_id):
    """When this member last paid (naive UTC), from the payment history, or None."""
    try:
        rows = (supabase.table("payments").select("created_at, paid_on").eq("member_id", member_id)
                .order("created_at", desc=True).limit(1).execute().data or [])
    except Exception:
        return None
    if not rows:
        return None
    t = pd.to_datetime(rows[0].get("created_at"), errors="coerce", utc=True, format="ISO8601")
    if pd.isna(t):
        t = pd.to_datetime(rows[0].get("paid_on"), errors="coerce")
        return None if pd.isna(t) else t
    return t.tz_localize(None)


def payment_kind(current_end, paid_on, is_first=False):
    if is_first:
        return "new"
    try:
        end = pd.to_datetime(current_end).date()
    except Exception:
        return "renewal"
    if pd.isna(pd.Timestamp(end)):
        return "renewal"
    return "recovered" if end < paid_on else "renewal"


NEW_MEMBER_DAYS = 45      # a first payment within this many days of joining is a joining payment


def member_joined_on(supabase, member_id):
    try:
        rows = (supabase.table("members").select("created_at").eq("id", member_id)
                .limit(1).execute().data or [])
    except Exception:
        return None
    if not rows:
        return None
    t = pd.to_datetime(rows[0].get("created_at"), errors="coerce", utc=True, format="ISO8601")
    return None if pd.isna(t) else t.tz_convert(gw.APP_TZ).date()


def is_first_payment(supabase, gym_id, member_id):
    """True when this member has never paid and joined recently: their first
    payment is a joining payment, not a renewal."""
    if not payments_ready(supabase, gym_id):
        return False
    if _last_payment_time(supabase, gym_id, member_id) is not None:
        return False
    joined = member_joined_on(supabase, member_id)
    return joined is not None and (gw.today_local() - joined).days <= NEW_MEMBER_DAYS


def record_payment(supabase, gym_id, member_id, name, amount, plan, start, method="Cash",
                   current_end=None, act=None, update_fee=False, note="", first=None, end=None):
    """Save a payment: the member's plan dates, the payment, and, for a renewal,
    the credit to the play that earned it. A new member's first payment is a
    joining payment and is never credited to a retention play."""
    paid_on = gw.today_local()
    new_end = end or (start + timedelta(days=gw.PLAN_DAYS[plan]))
    if first is None:
        first = is_first_payment(supabase, gym_id, member_id)
    kind = payment_kind(current_end, paid_on, is_first=first)
    play = None if first else find_creditable_play(supabase, gym_id, member_id, paid_on)

    # 1. the member's record is the source of truth for plan dates
    member_update = {"membership_end": new_end.isoformat(), "last_payment": float(amount)}
    if not first:      # a joining payment is not a renewal, so it doesn't count in the renewal rate
        member_update["last_renewed_on"] = paid_on.isoformat()
    supabase.table("members").update(member_update).eq("id", member_id).execute()
    if act:
        changes = {"membership_type": plan,
                   "renewal_due_days": int(min(max((new_end - paid_on).days, 0), 730))}
        if update_fee and amount > 0:
            changes["monthly_fee"] = round(float(amount) / gw.PLAN_MONTHS[plan], 2)
        supabase.table("member_activity").update(changes).eq("member_id", member_id).execute()

    # 2. the payment itself (one row, optionally credited to one play)
    row = {"gym_id": gym_id, "member_id": member_id, "amount": float(amount),
           "paid_on": paid_on.isoformat(), "covers_until": new_end.isoformat(), "plan": plan,
           "kind": kind, "method": method, "note": note or None,
           "action_id": play["id"] if play else None}
    saved = True
    try:
        supabase.table("payments").insert(row).execute()
    except Exception as error:
        if gw._is_duplicate_error(error) and play:      # play already credited elsewhere
            row["action_id"] = None
            play = None
            try:
                supabase.table("payments").insert(row).execute()
            except Exception:
                saved = False
        else:
            saved = False

    # 3. a confirmed payment is what closes the play as Retained
    msg = (f"Joining payment saved. {name} is active until {new_end:%d %b %Y}." if first
           else f"Renewal saved. {name} is active until {new_end:%d %b %Y}.")
    if play:
        if play.get("status") != "Done":
            gw.close_action(supabase, play["id"], "Retained",
                            (gw._text(play.get("note")) + " · " if play.get("note") else "")
                            + f"Renewed: {float(amount):,.0f} paid on {paid_on:%d %b}.")
        msg += (f" Credited to their {play['action_type']} play." if saved
                else f" Their {play['action_type']} play is marked Retained.")
    if kind == "recovered":
        msg += " Recorded as recovered revenue (their membership had lapsed)."
    if not saved:
        msg += " Run sql/phase3_revenue.sql to keep a full payment history."
    gw.bump_data_version()
    return msg


# ------------------------------------------------------------------ reporting
def renewal_rate(roster, days=30):
    """Of the memberships that came due in the last `days`, how many renewed."""
    if roster.empty or "membership_end" not in roster.columns:
        return None, 0, 0
    today = pd.Timestamp(gw.today_local())
    start = today - pd.Timedelta(days=days)
    renewed_on = pd.to_datetime(roster["last_renewed_on"] if "last_renewed_on" in roster.columns
                                else pd.Series(index=roster.index, dtype=object), errors="coerce")
    end = pd.to_datetime(roster["membership_end"], errors="coerce")
    renewed = int((renewed_on >= start).sum())
    lapsed = int(((end >= start) & (end < today)).sum())
    total = renewed + lapsed
    return (renewed / total if total else None), renewed, lapsed


def revenue_summary(supabase, gym_id, roster, days=30):
    """Verified revenue for the window. `source` says where the numbers came from."""
    out = {"source": "outcomes", "collected": 0.0, "renewals_n": 0, "recovered": 0.0,
           "recovered_n": 0, "retained_by_plays": 0.0, "retained_monthly": 0.0,
           "credited_n": 0, "by_play": {}, "days": days}
    rate, renewed, lapsed = renewal_rate(roster, days)
    out.update(renewal_rate=rate, renewed=renewed, lapsed=lapsed)
    pay = load_payments(supabase, gym_id)
    if pay is None:
        return out
    out["source"] = "payments"
    since = gw.today_local() - timedelta(days=days)
    win = pay[pay["paid_on"] >= since] if not pay.empty else pay
    if win.empty:
        return out
    win = win.drop_duplicates("id")
    out["collected"] = float(win["amount"].sum())
    out["renewals_n"] = int(win["kind"].isin(["renewal", "recovered"]).sum())
    rec = win[win["kind"] == "recovered"]
    out["recovered"], out["recovered_n"] = float(rec["amount"].sum()), len(rec)
    cred = win[win["action_id"].notna()].drop_duplicates("action_id")
    out["credited_n"] = len(cred)
    out["retained_by_plays"] = float(cred["amount"].sum())
    if not roster.empty and len(cred):
        fees = roster.set_index("id")["monthly_fee"]
        out["retained_monthly"] = float(
            fees.reindex(cred["member_id"].drop_duplicates()).fillna(0).sum())
        try:
            acts = (supabase.table("retention_actions").select("id, action_type")
                    .in_("id", list(cred["action_id"].astype(str))).execute().data or [])
            kind_of = {str(a["id"]): a["action_type"] for a in acts}
            for _, p in cred.iterrows():
                k = kind_of.get(str(p["action_id"]), "Other play")
                out["by_play"][k] = out["by_play"].get(k, 0.0) + float(p["amount"])
        except Exception:
            pass
    return out


# ------------------------------------------------------------------ views
RECENT_PAYMENT_DAYS = 7


def renewal_guard(supabase, gym_id, member_id, name, current_end, plan, key):
    """Stop accidental repeat renewals. Returns True when it's fine to save:
    either nothing looks like a duplicate, or the owner confirmed it's a separate payment."""
    reasons = []
    pay = load_payments(supabase, gym_id)
    if pay is not None and not pay.empty:
        mine = pay[pay["member_id"] == member_id]
        if len(mine):
            last = mine.iloc[0]
            if pd.notna(last["paid_on"]) and (gw.today_local() - last["paid_on"]).days <= RECENT_PAYMENT_DAYS:
                until = pd.to_datetime(last.get("covers_until"), errors="coerce")
                reasons.append(f"{name} already paid {last['amount']:,.0f} on {last['paid_on']:%d %b}"
                               + ("" if pd.isna(until) else f", covering until {until:%d %b %Y}") + ".")
    state = gw.membership_state(current_end)
    if state["days"] is not None and state["days"] > gw.PLAN_DAYS.get(plan, 30):
        reasons.append(f"Their membership is already paid until {state['end']:%d %b %Y}, "
                       f"more than one {gw.plan_phrase(plan)} period ahead.")
    if not reasons:
        return True
    st.warning(" ".join(reasons) + " Saving again adds another period on top.")
    return st.checkbox("Yes, this is a separate new payment", key=f"guard_{key}_{member_id}")


def render_record_payment(supabase, gym_id, roster):
    """Quick 'record a renewal' form for the Payments page."""
    st.markdown('<div class="section-label">RECORD A RENEWAL OR PAYMENT</div>',
                unsafe_allow_html=True)
    if roster.empty:
        st.info("Add members first.")
        return
    names = roster.set_index("id")["full_name"].to_dict()
    with st.container(border=True, key="card_pay_record"):
        c1, c2, c3 = st.columns([2, 1, 1])
        ordered = sorted(names, key=lambda i: str(names[i]).lower())
        form_n = st.session_state.get("rp_n", 0)
        mid = c1.selectbox("Member", ordered, index=None, placeholder="Choose a member",
                           format_func=lambda i: names[i], key=f"rp_member_{form_n}")
        if mid is None:
            st.caption("Pick the member who paid. New members' first payment is recorded as a "
                       "joining payment; later ones as renewals.")
            return
        r = roster[roster["id"] == mid].iloc[0]
        first = is_first_payment(supabase, gym_id, mid)
        plans = gw.PLANS
        cur = gw.plan_name(r.get("membership_type"))
        plan = c2.selectbox("Plan", plans, index=plans.index(cur), key=f"rp_plan_{mid}")
        method = c3.selectbox("Paid by", PAYMENT_METHODS, key="rp_method")
        state = gw.membership_state(r.get("membership_end"))
        if first:
            start_default = member_joined_on(supabase, mid) or date.today()
        else:
            start_default = state["end"] if state["end"] and state["end"] >= date.today() else date.today()
        d1, d2 = st.columns(2)
        start = d1.date_input("New period starts", value=start_default,
                              key=f"rp_start_{mid}_{start_default}")
        amount = d2.number_input("Amount paid", min_value=0.0, step=500.0,
                                 value=float((r.get("monthly_fee") or 0) * gw.PLAN_MONTHS[plan]),
                                 key=f"rp_amt_{mid}_{plan}")
        new_end = start + timedelta(days=gw.PLAN_DAYS[plan])
        play = None if first else find_creditable_play(supabase, gym_id, mid, gw.today_local())
        if first:
            hint = (f"Runs until **{new_end:%d %b %Y}**. This is **{names[mid]}'s first payment**, "
                    "so it's recorded as a joining payment, not a renewal.")
        else:
            hint = (f"Runs until **{new_end:%d %b %Y}**. "
                    + (f"This renewal will be credited to their **{play['action_type']}** play."
                       if play else "No recent play to credit, so it counts as a renewal only."))
        st.caption(hint)
        ok = renewal_guard(supabase, gym_id, mid, names[mid], r.get("membership_end"), plan, "rp")
        if st.button("Save payment", key="rp_save", type="primary", disabled=not ok):
            try:
                st.session_state["pay_flash"] = record_payment(
                    supabase, gym_id, mid, names[mid], amount, plan, start, method,
                    current_end=r.get("membership_end"), act=True, first=first)
                st.session_state["rp_n"] = form_n + 1      # fresh, empty form after saving
            except Exception as error:
                st.session_state["pay_flash"] = f"Could not save the payment: {error}"
            st.rerun()


PAYMENTS_TABLE_CSS = """
.gp-table-wrap { border: 1px solid rgba(255,255,255,0.09); border-radius: 16px; overflow: hidden;
    background: #10172A; }
.gp-table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
.gp-table th { text-align: left; font-size: 11px; letter-spacing: .8px; text-transform: uppercase;
    color: #93A1B8; font-weight: 700; padding: 11px 14px; background: rgba(255,255,255,0.03);
    border-bottom: 1px solid rgba(255,255,255,0.08); white-space: nowrap; }
.gp-table td { padding: 11px 14px; color: #E6ECF5; border-bottom: 1px solid rgba(255,255,255,0.06);
    vertical-align: middle; }
.gp-table tr:last-child td { border-bottom: 0; }
.gp-table td.num { text-align: right; font-variant-numeric: tabular-nums; font-weight: 700; color: #F4F7FB; }
.gp-table th.num { text-align: right; }
.gp-table .sub { display: block; font-size: 11.5px; color: #93A1B8; margin-top: 2px; }
.gp-table-foot { display: flex; justify-content: space-between; gap: 10px; flex-wrap: wrap;
    padding: 10px 14px; font-size: 12.5px; color: #93A1B8; border-top: 1px solid rgba(255,255,255,0.08); }
.gp-table-foot b { color: #F4F7FB; }
@media (max-width: 700px) {
    .gp-table thead { display: none; }
    .gp-table, .gp-table tbody, .gp-table tr, .gp-table td { display: block; width: 100%; box-sizing: border-box; }
    .gp-table tr { padding: 10px 14px; border-bottom: 1px solid rgba(255,255,255,0.07); }
    .gp-table td { border: 0; padding: 2px 0; }
    .gp-table td.num { text-align: left; font-size: 16px; }
    .gp-table td[data-l]::before { content: attr(data-l) ": "; color: #93A1B8; font-size: 12px; }
    .gp-table td.num, .gp-table td.kind { display: inline-block; width: auto; margin: 4px 10px 2px 0;
        vertical-align: middle; }
    .gp-table td.none { display: none; }
}
"""


def render_recent_payments(supabase, gym_id, roster):
    st.markdown('<div class="section-label">RECENT PAYMENTS</div>', unsafe_allow_html=True)
    pay = load_payments(supabase, gym_id)
    if pay is None:
        st.info("Run sql/phase3_revenue.sql in Supabase to keep a full payment history "
                "and credit renewals to the plays that earned them.")
        return
    if pay.empty:
        st.caption("No payments recorded yet. Record one above, or from a member's profile.")
        return
    names = roster.set_index("id")["full_name"].to_dict() if not roster.empty else {}
    plays = {}
    ids = [str(x) for x in pay["action_id"].dropna().tolist() if not gw._blank(x)]
    if ids:
        try:
            rows = (supabase.table("retention_actions").select("id, action_type")
                    .in_("id", ids[:200]).execute().data or [])
            plays = {str(r["id"]): r["action_type"] for r in rows}
        except Exception:
            plays = {}
    show = st.session_state.get("pay_rows", 10)
    body = []
    for _, p in pay.head(show).iterrows():
        when = f"{p['paid_on']:%d %b %Y}" if pd.notna(p["paid_on"]) else "—"
        who = names.get(p["member_id"], "Former member")
        plan = gw._text(p.get("plan"))
        until_d = pd.to_datetime(p.get("covers_until"), errors="coerce")
        until = "" if pd.isna(until_d) else f"{until_d:%d %b %Y}"
        credit = ("—" if gw._blank(p["action_id"]) else
                  gw.chip(plays.get(str(p["action_id"]), "A play"), "lime", dot=True))
        kind = PAYMENT_KINDS.get(p["kind"], "Payment")
        tone = {"recovered": "amber", "new": "lime"}.get(p["kind"], "cyan")
        body.append(
            f'<tr><td data-l="Date">{gw._esc(when)}</td>'
            f'<td><b>{gw._esc(who)}</b><span class="sub">{gw._esc(plan)}'
            f'{" · until " + gw._esc(until) if until else ""}</span></td>'
            f'<td class="num">{p["amount"]:,.0f}</td>'
            f'<td class="kind">{gw.chip(kind, tone)}</td>'
            f'<td data-l="Paid by">{gw._esc(gw._text(p.get("method"), "—"))}</td>'
            f'<td data-l="Credited to" class="{"none" if credit == "—" else ""}">{credit}</td></tr>')
    since = gw.today_local() - timedelta(days=30)
    month = pay[pay["paid_on"] >= since]
    gw._md("<style>" + PAYMENTS_TABLE_CSS + "</style>"
           '<div class="gp-table-wrap"><table class="gp-table"><thead><tr>'
           '<th>Date</th><th>Member</th><th class="num">Amount</th><th>Type</th><th>Paid by</th>'
           '<th>Credited to</th></tr></thead><tbody>' + "".join(body) + "</tbody></table>"
           f'<div class="gp-table-foot"><span>Last 30 days: <b>{month["amount"].sum():,.0f}</b> '
           f'from <b>{len(month)}</b> payment(s)</span><span>Showing {min(show, len(pay))} of '
           f'{len(pay)}</span></div></div>')
    c1, c2 = st.columns([1, 1])
    if len(pay) > show:
        c1.button("Show more payments", key="pay_more", type="tertiary",
                  on_click=gw._bump, args=("pay_rows", 10, 20))
    try:
        import gympulse_pilot as gp
        import gympulse_reports as rp
        tables = [t for t in gp.export_tables(supabase, gym_id, roster, None) if t[0] == "Payments"]
        if tables:
            with c2:
                rp.download_link("Payment history (Excel)", rp.build_xlsx(tables, "Payment history"),
                                 f"GymPulse-payments-{gw.today_local():%Y-%m-%d}.xlsx", rp.XLSX, "pay_xlsx")
    except Exception:
        pass


def render_revenue_outcomes(supabase, gym_id, roster):
    """Business Insights: what retention work is worth, from confirmed payments."""
    rev = revenue_summary(supabase, gym_id, roster)
    st.markdown('<div class="section-label">REVENUE OUTCOMES · LAST 30 DAYS</div>',
                unsafe_allow_html=True)
    rate = "n/a" if rev["renewal_rate"] is None else f"{rev['renewal_rate']:.0%}"
    if rev["source"] == "payments":
        gw.kpi_row([
            ("Collected", f"{rev['collected']:,.0f}", "cyan", f"{rev['renewals_n']} renewal payment(s)"),
            ("Retained by plays", f"{rev['retained_by_plays']:,.0f}", "lime",
             f"{rev['credited_n']} renewal(s) credited to a play"),
            ("Recovered", f"{rev['recovered']:,.0f}", "amber",
             f"{rev['recovered_n']} lapsed member(s) came back"),
            ("Renewal rate", rate, "white", f"{rev['renewed']} renewed · {rev['lapsed']} lapsed"),
        ])
        st.caption("All figures are recorded payments. A renewal is credited to a play only if the "
                   f"member was worked in the {ATTRIBUTION_WINDOW_DAYS} days before paying, and each "
                   "payment and each play is credited once, so nothing is double-counted. Credit "
                   "shows the play was involved, not that the member would have left without it.")
        if rev["by_play"]:
            rows = sorted(rev["by_play"].items(), key=lambda kv: kv[1], reverse=True)
            top = max(v for _, v in rows) or 1
            gw._md('<div class="cc-brief" style="border-color:rgba(255,255,255,0.08)">'
                   '<div class="cc-brief-title" style="margin-bottom:8px">Revenue credited by play</div>'
                   + "".join(f'<div class="cc-play"><div class="cc-play-name">{gw._esc(k)}</div>'
                             f'<div class="cc-play-bar"><span style="width:{round(v / top * 100)}%"></span></div>'
                             f'<div class="cc-play-rate">{v:,.0f}</div></div>' for k, v in rows)
                   + "</div>")
    else:
        gw.kpi_row([
            ("Renewal rate", rate, "white", f"{rev['renewed']} renewed · {rev['lapsed']} lapsed"),
            ("Renewed (30 days)", rev["renewed"], "lime", "From renewal dates on profiles"),
        ])
        st.info("Run sql/phase3_revenue.sql in Supabase to track every payment, credit renewals "
                "to the plays that earned them and report recovered revenue.")
