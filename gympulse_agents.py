"""GymPulse AI · sales agents: referral codes and the commission owed to each agent.

An agent introduces gyms. A gym counts as theirs when it signs up with the agent's code (the optional
"Referral code" box on sign-up, or a link like usegympulseai.com/?ref=AGENT-TUNDE), or when the founder
links the gym to the agent in Admin → Agents.

Commission (the agent agreement):
  * 50% of the gym's first paid month, then 10% of each later payment, for 12 months from the first payment.
  * A yearly payment earns 15% of that payment, once.
  * Only paid invoices count (billing_invoices.status = 'paid'), so the free trial earns nothing and a
    cancelled invoice earns nothing. A refund is entered as a negative adjustment.

Everything is kept in platform_settings under "sales_agents", which gyms can't read:
  {"agents":  {CODE: {"name", "phone", "email", "since", "active", "note"}},
   "gyms":    {gym_id: {"code", "since", "by"}},             # links set by the founder (override sign-up codes)
   "adjust":  [{"code", "month", "amount", "note", "at"}],   # refunds and corrections, + or -
   "paid":    {CODE: {"YYYY-MM": {"amount", "on"}}}}          # what has been paid out
"""
import csv
import io
import re
from datetime import date, datetime, timedelta, timezone

import streamlit as st

import gympulse_workspaces as gw

KEY = "sales_agents"
FIRST_RATE, LATER_RATE, YEARLY_RATE, WINDOW_DAYS = 0.50, 0.10, 0.15, 365
REF_PARAM = "ref"


# ------------------------------------------------------------------ codes
def clean_code(value):
    """AGENT-TUNDE style: letters, numbers and dashes, upper case, at most 24 characters."""
    code = re.sub(r"[^A-Z0-9-]", "", gw._text(value).strip().upper().replace(" ", "-"))
    return re.sub(r"-{2,}", "-", code).strip("-")[:24]


def remember_ref_param():
    """Keep ?ref=CODE from the landing link for the sign-up form (query params are cleared later)."""
    try:
        code = clean_code(st.query_params.get(REF_PARAM))
        if code:
            st.session_state["ref_code"] = code
    except Exception:
        pass


# ------------------------------------------------------------------ data
def load(sc):
    try:
        rows = sc.table("platform_settings").select("value").eq("key", KEY).limit(1).execute().data
        v = dict(rows[0]["value"] or {}) if rows else {}
    except Exception:
        v = {}
    return {"agents": dict(v.get("agents") or {}), "gyms": dict(v.get("gyms") or {}),
            "adjust": list(v.get("adjust") or []), "paid": dict(v.get("paid") or {})}


def save(sc, data):
    sc.table("platform_settings").upsert({"key": KEY, "value": data,
                                          "updated_at": datetime.now(timezone.utc).isoformat()},
                                         on_conflict="key").execute()


def attribution(gyms, data):
    """{gym_id: code}. A link set by the founder wins; otherwise the code the owner entered at sign-up,
    if it belongs to an agent. Returns (links, unknown) where unknown = {gym_id: code nobody owns}."""
    links, unknown = {}, {}
    for g in gyms:
        gid = str(g["gym"]["id"])
        set_by_founder = (data["gyms"].get(gid) or {}).get("code")
        if set_by_founder is not None:
            if set_by_founder:                       # "" = the founder said "no agent"
                links[gid] = set_by_founder
            continue
        code = clean_code(g.get("ref_code"))
        if code and code in data["agents"]:
            links[gid] = code
        elif code:
            unknown[gid] = code
    return links, unknown


def _paid_day(inv):
    try:
        return datetime.fromisoformat(str(inv.get("paid_at")).replace("Z", "+00:00")).date()
    except Exception:
        return None


def commission_lines(invoices):
    """One line per paid invoice of one gym, oldest first: (invoice, paid day, rate text, commission)."""
    paid = sorted([i for i in invoices if i.get("status") == "paid" and _paid_day(i)], key=_paid_day)
    if not paid:
        return []
    first_day = _paid_day(paid[0])
    out = []
    for n, inv in enumerate(paid):
        day = _paid_day(inv)
        if (day - first_day).days >= WINDOW_DAYS:
            break
        amount = float(inv.get("amount") or 0)
        months = max(int(inv.get("months") or 1), 1)
        if inv.get("period") == "yearly":
            rate, value = "15% of a yearly payment", amount * YEARLY_RATE
        elif n == 0:
            per_month = amount / months
            value = per_month * FIRST_RATE + per_month * (months - 1) * LATER_RATE
            rate = "50% of the first month" + (f", 10% of {months - 1} more" if months > 1 else "")
        else:
            rate, value = "10%", amount * LATER_RATE
        out.append((inv, day, rate, round(value, 2)))
    return out


def statement(sc, gyms, data, invoices=None):
    """Every commission line for every agent: dicts with code, month, gym, plan, paid_on, amount, rate, commission."""
    links, _ = attribution(gyms, data)
    names = {str(g["gym"]["id"]): g["name"] for g in gyms}
    if invoices is None:
        try:
            invoices = sc.table("billing_invoices").select("*").in_("gym_id", list(links)).execute().data \
                if links else []
        except Exception:
            invoices = []
    by_gym = {}
    for inv in invoices:
        by_gym.setdefault(str(inv.get("gym_id")), []).append(inv)
    rows = []
    for gid, code in links.items():
        for inv, day, rate, value in commission_lines(by_gym.get(gid, [])):
            rows.append({"code": code, "month": f"{day:%Y-%m}", "gym": names.get(gid, "Gym"),
                         "plan": f"{gw._text(inv.get('plan'))} ({gw._text(inv.get('period'))})",
                         "paid_on": day.isoformat(), "amount": float(inv.get("amount") or 0),
                         "rate": rate, "commission": value})
    for a in data["adjust"]:
        rows.append({"code": a.get("code"), "month": a.get("month"), "gym": "Adjustment",
                     "plan": gw._text(a.get("note")), "paid_on": (a.get("at") or "")[:10], "amount": 0.0,
                     "rate": "", "commission": float(a.get("amount") or 0)})
    return sorted(rows, key=lambda r: (r["month"], r["paid_on"]), reverse=True)


def owed(rows, data, code, month):
    """What this agent earned in a month, and what is still to pay for it."""
    earned = round(sum(r["commission"] for r in rows if r["code"] == code and r["month"] == month), 2)
    paid = float(((data["paid"].get(code) or {}).get(month) or {}).get("amount") or 0)
    return earned, round(earned - paid, 2)


def _money(x):
    return f"₦{x:,.0f}" if x >= 0 else f"−₦{-x:,.0f}"


def _month_label(m):
    try:
        return datetime.strptime(m, "%Y-%m").strftime("%B %Y")
    except Exception:
        return m


def _nice_day(iso):
    try:
        return date.fromisoformat(iso).strftime("%-d %b %Y")
    except Exception:
        return iso


def _last_month(today=None):
    today = today or gw.today_local()
    first = date(today.year, today.month, 1)
    return f"{first - timedelta(days=1):%Y-%m}"


# ------------------------------------------------------------------ admin page
def render_admin(sc, gyms, audit):
    """Admin → Agents: add agents, link gyms, and see what each agent is owed this month."""
    data = load(sc)
    rows = statement(sc, gyms, data)
    links, unknown = attribution(gyms, data)
    agents = data["agents"]
    names = {str(g["gym"]["id"]): g["name"] for g in gyms}
    month = _last_month()

    st.caption("Agents earn 50% of a gym's first paid month, then 10% of each payment for 12 months. A yearly "
               "payment earns 15%, once. Only cleared payments count. Pay by the 5th for the month before.")

    to_pay = sum(max(owed(rows, data, c, month)[1], 0) for c in agents)
    gw.kpi_row([("Agents", str(sum(1 for a in agents.values() if a.get("active", True))), "lime", "active"),
                ("Gyms from agents", str(len(links)), "cyan", "linked to a code"),
                (f"To pay for {_month_label(month)}", _money(to_pay), "lime", "by the 5th")])

    if unknown:
        st.warning("These gyms signed up with a code no agent has: "
                   + ", ".join(f"{names.get(g, 'Gym')} ({c})" for g, c in unknown.items())
                   + ". Add the agent with that code, or link the gym below.")

    # ---- this month, per agent
    st.markdown("**What each agent is owed**")
    months = sorted({r["month"] for r in rows} | {month}, reverse=True)
    pick = st.selectbox("Month", months, index=months.index(month), format_func=_month_label, key="ag_month")
    summary = []
    for code, a in sorted(agents.items()):
        earned, left = owed(rows, data, code, pick)
        summary.append({"Agent": a.get("name") or code, "Code": code,
                        "Gyms": str(sum(1 for c in links.values() if c == code)),
                        "Earned": _money(earned), "Still to pay": _money(left),
                        "Status": "Paid" if earned and left <= 0 else ("To pay" if left > 0 else "Nothing due")})
    gw.table(summary, pills=("Status",), empty="No agents yet. Add your first one below.")

    if agents:
        with st.form("ag_pay"):
            c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
            code = c1.selectbox("Agent", sorted(agents), format_func=lambda c: f"{agents[c].get('name') or c} ({c})",
                                key="ag_pay_code")
            mark = c2.form_submit_button(f"Mark {_month_label(pick)} as paid", use_container_width=True)
        if mark:
            earned, _ = owed(rows, data, code, pick)
            data["paid"].setdefault(code, {})[pick] = {"amount": earned, "on": gw.today_local().isoformat()}
            save(sc, data)
            audit(sc, "agent_paid", {"gym": {"id": None}, "name": agents[code].get("name") or code, "email": None},
                  {"code": code, "month": pick, "amount": earned})
            st.session_state["adm_flash"] = f"Marked {_money(earned)} for {_month_label(pick)} as paid to {code}."
            st.rerun()

    # ---- statement
    if rows:
        st.markdown("**Statement**")
        who = st.selectbox("Statement for", ["Everyone"] + sorted(agents), key="ag_stmt",
                           format_func=lambda c: c if c == "Everyone" else f"{agents[c].get('name') or c} ({c})")
        lines = [r for r in rows if who == "Everyone" or r["code"] == who]
        lines = [r for r in lines if r["month"] == pick]
        gw.table([{"Gym": r["gym"], "Agent": r["code"], "Plan": r["plan"], "Paid on": _nice_day(r["paid_on"]),
                   "Gym paid": _money(r["amount"]) if r["amount"] else "", "Rate": r["rate"],
                   "Commission": _money(r["commission"])} for r in lines],
                 empty=f"No commission in {_month_label(pick)}.")
        if lines:
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["Month", "Agent code", "Gym", "Plan", "Paid on", "Gym paid (NGN)", "Rate", "Commission (NGN)"])
            for r in lines:
                w.writerow([_month_label(r["month"]), r["code"], r["gym"], r["plan"], r["paid_on"],
                            f"{r['amount']:.2f}", r["rate"], f"{r['commission']:.2f}"])
            st.download_button("Download statement (CSV)", buf.getvalue(), key="ag_csv", mime="text/csv",
                               file_name=f"gympulse-commission-{who.lower()}-{pick}.csv")

    # ---- manage
    with st.expander("Add or edit an agent", icon=":material/person_add:"):
        with st.form("ag_form"):
            c1, c2 = st.columns(2)
            name = c1.text_input("Full name", placeholder="e.g. Tunde Bakare")
            code_in = c2.text_input("Referral code", placeholder="e.g. AGENT-TUNDE",
                                    help="Letters, numbers and dashes. Use the same code again to edit an agent.")
            c3, c4 = st.columns(2)
            phone = c3.text_input("WhatsApp number", placeholder="e.g. 0803 000 0000")
            email = c4.text_input("Email (optional)")
            note = st.text_input("Note (for you)", placeholder="e.g. Agreement signed 24 Nov, covers Lekki and VI")
            active = st.checkbox("Active", value=True)
            c5, c6 = st.columns(2)
            save_btn = c5.form_submit_button("Save agent", type="primary", use_container_width=True)
            remove = c6.form_submit_button("Remove agent", use_container_width=True)
        if save_btn or remove:
            code = clean_code(code_in)
            if not code:
                st.error("Enter a referral code.")
            elif remove:
                if code not in agents:
                    st.error(f"No agent has the code {code}.")
                else:
                    agents.pop(code)
                    save(sc, data)
                    st.session_state["adm_flash"] = f"Removed {code}. Their past statements stay in the log."
                    st.rerun()
            elif not name.strip() and code not in agents:
                st.error("Enter the agent's name.")
            else:
                old = agents.get(code, {})
                agents[code] = {"name": name.strip() or old.get("name", ""), "phone": phone.strip() or old.get("phone", ""),
                                "email": email.strip() or old.get("email", ""), "note": note.strip()[:200] or old.get("note", ""),
                                "active": bool(active), "since": old.get("since") or gw.today_local().isoformat()}
                save(sc, data)
                audit(sc, "agent_saved", {"gym": {"id": None}, "name": agents[code]["name"] or code, "email": None},
                      {"code": code})
                st.session_state["adm_flash"] = (f"Saved {code}. Their sign-up link is "
                                                 f"usegympulseai.com/?{REF_PARAM}={code}")
                st.rerun()
        if agents:
            gw.table([{"Code": c, "Name": a.get("name", ""), "WhatsApp": a.get("phone", ""),
                       "Since": a.get("since", ""), "Status": "Active" if a.get("active", True) else "Paused",
                       "Sign-up link": f"usegympulseai.com/?{REF_PARAM}={c}"} for c, a in sorted(agents.items())],
                     pills=("Status",))

    with st.expander("Link a gym to an agent", icon=":material/link:"):
        st.caption("For a gym that forgot the code at sign-up, or to correct one. Choose No agent to unlink.")
        with st.form("ag_link"):
            gid = st.selectbox("Gym", list(names), format_func=names.get, key="ag_link_gym")
            options = [""] + sorted(agents)
            code = st.selectbox("Agent", options, key="ag_link_code",
                                format_func=lambda c: "No agent" if not c else f"{agents[c].get('name') or c} ({c})")
            link = st.form_submit_button("Save link", type="primary")
        if link:
            data["gyms"][gid] = {"code": code, "since": gw.today_local().isoformat(), "by": "admin"}
            save(sc, data)
            audit(sc, "agent_linked", next((g for g in gyms if str(g["gym"]["id"]) == gid),
                                           {"gym": {"id": gid}, "name": names.get(gid), "email": None}),
                  {"code": code or None})
            st.session_state["adm_flash"] = (f"{names.get(gid)} is now linked to {code}." if code else
                                             f"{names.get(gid)} has no agent now.")
            st.rerun()
        if links:
            gw.table([{"Gym": names.get(g, "Gym"), "Agent": c,
                       "How": "Linked by you" if (data["gyms"].get(g) or {}).get("code") else "Code at sign-up"}
                      for g, c in sorted(links.items(), key=lambda x: names.get(x[0], ""))])

    with st.expander("Refund or correction", icon=":material/undo:"):
        st.caption("A refunded payment: enter its commission as a minus amount in the month you refund it. "
                   "It comes off that month's total.")
        if not agents:
            st.caption("Add an agent first.")
        else:
            with st.form("ag_adj"):
                c1, c2 = st.columns(2)
                code = c1.selectbox("Agent", sorted(agents), key="ag_adj_code")
                amount = c2.number_input("Amount (₦, minus to take off)", value=0.0, step=1000.0)
                c3, c4 = st.columns(2)
                m = c3.selectbox("Month", sorted(set(months) | {f"{gw.today_local():%Y-%m}"}, reverse=True),
                                 format_func=_month_label, key="ag_adj_month")
                note = c4.text_input("Reason", placeholder="e.g. Refund to Lekki branch, 3 Dec")
                add = st.form_submit_button("Add", type="primary")
            if add:
                if not amount or not note.strip():
                    st.error("Enter an amount and a reason.")
                else:
                    data["adjust"].append({"code": code, "month": m, "amount": float(amount), "note": note.strip()[:200],
                                           "at": datetime.now(timezone.utc).isoformat()})
                    save(sc, data)
                    st.session_state["adm_flash"] = f"Added {_money(float(amount))} for {code} in {_month_label(m)}."
                    st.rerun()
