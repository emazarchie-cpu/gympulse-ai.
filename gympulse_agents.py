"""GymPulse AI · sales agents: referral codes and the commission owed to each agent.

An agent introduces gyms. A gym counts as theirs when it signs up with the agent's code (the optional
"Referral code" box on sign-up, or a link like usegympulseai.com/?ref=AGENT-TUNDE), or when the founder
links the gym to the agent in Admin → Agents.

Commission (the agent agreement):
  * 50% of the gym's first paid month, then 10% of each later payment, for 12 months from the first payment.
  * A yearly payment earns 15% of that payment, once.
  * 5-gym bonus: a one-off NGN 50,000 when 5 of the agent's gyms have been set up and made their first payment,
    counted in the month the fifth gym qualifies.
  * Only paid invoices count (billing_invoices.status = 'paid'), so the free trial earns nothing and a
    cancelled invoice earns nothing. A refund is entered as a negative adjustment.

Everything is kept in platform_settings under "sales_agents", which gyms can't read:
  {"agents":  {CODE: {"name", "phone", "email", "since", "active", "note"}},
   "gyms":    {gym_id: {"code", "since", "by"}},             # links set by the founder (override sign-up codes)
   "adjust":  [{"code", "month", "amount", "note", "at"}],   # refunds and corrections, + or -
   "paid":    {CODE: {"YYYY-MM": {"amount", "on"}}},          # what has been paid out
   "setup":   {gym_id: {"done_on", "by"}}}                    # set-up confirmed by the founder

The 50% for the first month is held until the agent has set the gym up (members loaded, check-ins recorded on
at least SETUP_DAYS different days) and the founder has confirmed it. It then counts in the later of the
payment month and the month set-up was confirmed.
"""
import csv
import io
import re
from datetime import date, datetime, timedelta, timezone

import streamlit as st

import gympulse_workspaces as gw

KEY = "sales_agents"
FIRST_RATE, LATER_RATE, YEARLY_RATE, WINDOW_DAYS = 0.50, 0.10, 0.15, 365
BONUS_GYMS, BONUS_AMOUNT = 5, 50000      # one-off bonus when 5 of an agent's gyms are set up and have paid
REF_PARAM = "ref"
SIGN_PARAM = "agent"    # usegympulseai.com/?agent=TOKEN: the agent's private link to read and sign the agreement
SETUP_DAYS = 5          # check-in days needed before set-up can be confirmed


# ------------------------------------------------------------------ codes
def clean_code(value):
    """AGENT-TUNDE style: letters, numbers and dashes, upper case, at most 24 characters."""
    code = re.sub(r"[^A-Z0-9-]", "", gw._text(value).strip().upper().replace(" ", "-"))
    return re.sub(r"-{2,}", "-", code).strip("-")[:24]


def new_token():
    import secrets
    return secrets.token_urlsafe(12)


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
            "adjust": list(v.get("adjust") or []), "paid": dict(v.get("paid") or {}),
            "setup": dict(v.get("setup") or {})}


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
    rows, qualified = [], {}
    for gid, code in links.items():
        done = (data.get("setup") or {}).get(gid, {}).get("done_on")
        lines = commission_lines(by_gym.get(gid, []))
        if done and lines:                               # set up and paid: counts towards the 5-gym bonus
            try:
                qualified.setdefault(code, []).append(max(lines[0][1], date.fromisoformat(done[:10])))
            except ValueError:
                pass
        for n, (inv, day, rate, value) in enumerate(lines):
            month, held = f"{day:%Y-%m}", False
            if n == 0:                                       # the first payment waits for set-up
                if not done:
                    held, month = True, "held"
                else:
                    month = max(month, done[:7])
            rows.append({"code": code, "month": month, "gym": names.get(gid, "Gym"),
                         "plan": f"{gw._text(inv.get('plan'))} ({gw._text(inv.get('period'))})",
                         "paid_on": day.isoformat(), "amount": float(inv.get("amount") or 0),
                         "rate": rate + (", held until set-up is confirmed" if held else ""),
                         "commission": value, "held": held})
    for code, days in qualified.items():
        if len(days) >= BONUS_GYMS:
            d = sorted(days)[BONUS_GYMS - 1]
            rows.append({"code": code, "month": f"{d:%Y-%m}", "gym": f"{BONUS_GYMS}-gym bonus",
                         "plan": f"{BONUS_GYMS} gyms set up and paid", "paid_on": d.isoformat(), "amount": 0.0,
                         "rate": "one-off bonus", "commission": float(BONUS_AMOUNT), "held": False})
    for a in data["adjust"]:
        rows.append({"code": a.get("code"), "month": a.get("month"), "gym": "Adjustment",
                     "plan": gw._text(a.get("note")), "paid_on": (a.get("at") or "")[:10], "amount": 0.0,
                     "rate": "", "commission": float(a.get("amount") or 0), "held": False})
    return sorted(rows, key=lambda r: (r["month"], r["paid_on"]), reverse=True)


def setup_status(sc, gym_id, today=None):
    """What the set-up checks show for one gym: members loaded and check-in days in the last 30 days."""
    today = today or gw.today_local()
    out = {"members": 0, "checkin_days": 0}
    try:
        r = sc.table("members").select("id", count="exact").eq("gym_id", gym_id).limit(1).execute()
        out["members"] = int(getattr(r, "count", None) or len(r.data or []))
    except Exception:
        pass
    try:
        since = (today - timedelta(days=30)).isoformat()
        rows = (sc.table("checkins").select("checked_in_at").eq("gym_id", gym_id).gte("checked_in_at", since)
                .limit(5000).execute().data or [])
        out["checkin_days"] = len({str(x.get("checked_in_at"))[:10] for x in rows if x.get("checked_in_at")})
    except Exception:
        pass
    out["ready"] = out["members"] > 0 and out["checkin_days"] >= SETUP_DAYS
    return out


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

    st.caption("Agents set gyms up and earn 50% of a gym's first paid month once set-up is confirmed, then 10% of "
               "each payment for 12 months. A yearly payment earns 15%, once. 5 gyms set up and paid earn a one-off "
               "₦50,000 bonus. Only cleared payments count. Pay by "
               "the 5th for the month before.")

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
    months = sorted({r["month"] for r in rows if r["month"] != "held"} | {month}, reverse=True)
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

    # ---- set-up: the first month's 50% is held until the agent has set the gym up
    if links:
        st.markdown("**Set-up**")
        st.caption(f"An agent's 50% for a gym's first month is paid once the gym is set up: members loaded and "
                   f"check-ins recorded on at least {SETUP_DAYS} different days in the last 30. Confirm it here.")
        status = {gid: setup_status(sc, gid) for gid in links}
        held = {r["gym"]: r["commission"] for r in rows if r.get("held")}
        gw.table([{"Gym": names.get(g, "Gym"), "Agent": c, "Members": f"{status[g]['members']:,}",
                   "Check-in days": f"{status[g]['checkin_days']} of {SETUP_DAYS}",
                   "Held": _money(held[names.get(g, "Gym")]) if names.get(g, "Gym") in held else "",
                   "Set-up": ("Confirmed" if (data["setup"].get(g) or {}).get("done_on") else
                              "Ready to confirm" if status[g]["ready"] else "In progress")}
                  for g, c in sorted(links.items(), key=lambda x: names.get(x[0], ""))],
                 pills={"Set-up": {"Confirmed": "lime", "Ready to confirm": "cyan", "In progress": "amber"}})
        waiting = [g for g in links if not (data["setup"].get(g) or {}).get("done_on")]
        if waiting:
            with st.form("ag_setup"):
                c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
                g = c1.selectbox("Gym", waiting, format_func=lambda x: names.get(x, "Gym"), key="ag_setup_gym")
                ok = c2.form_submit_button("Confirm set-up is done", type="primary", use_container_width=True)
            if ok:
                if not status[g]["ready"]:
                    st.error(f"Not yet: {names.get(g)} needs members loaded and check-ins on {SETUP_DAYS} "
                             f"different days (it has {status[g]['checkin_days']}).")
                else:
                    data["setup"][g] = {"done_on": gw.today_local().isoformat(), "by": "admin"}
                    save(sc, data)
                    audit(sc, "agent_setup_confirmed", next((x for x in gyms if str(x["gym"]["id"]) == g),
                                                            {"gym": {"id": g}, "name": names.get(g), "email": None}),
                          {"code": links[g]})
                    st.session_state["adm_flash"] = f"Set-up confirmed for {names.get(g)}. Any held 50% now counts."
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
            name = c1.text_input("Name (optional)", placeholder="They add their full name when they sign",
                                 help="Leave blank: the agent types their full legal name when they sign.")
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
            else:
                old = agents.get(code, {})
                agents[code] = {"name": name.strip() or old.get("name", ""), "phone": phone.strip() or old.get("phone", ""),
                                "email": email.strip() or old.get("email", ""), "note": note.strip()[:200] or old.get("note", ""),
                                "active": bool(active), "since": old.get("since") or gw.today_local().isoformat(),
                                "token": old.get("token") or new_token(), "signed": old.get("signed")}
                save(sc, data)
                audit(sc, "agent_saved", {"gym": {"id": None}, "name": agents[code]["name"] or code, "email": None},
                      {"code": code})
                st.session_state["adm_flash"] = (f"Saved {code}. Send them their agreement link from the list "
                                                 "below: they add their name and sign on their phone.")
                st.rerun()
        if agents:
            gw.table([{"Code": c, "Name": a.get("name") or "Adds it when signing", "WhatsApp": a.get("phone", ""),
                       "Agreement": "Signed" if a.get("signed") else "Not signed yet",
                       "Status": "Active" if a.get("active", True) else "Paused"} for c, a in sorted(agents.items())],
                     pills={"Agreement": {"Signed": "lime", "Not signed yet": "amber"},
                            "Status": {"Active": "lime", "Paused": "amber"}})

    if agents:
        with st.expander("Agreements", icon=":material/contract:"):
            pick_a = st.selectbox("Agent", sorted(agents), key="ag_doc_code",
                                  format_func=lambda c: f"{agents[c].get('name') or c} ({c})")
            a = agents[pick_a]
            if not a.get("token"):                     # agents added before signing links existed
                a["token"] = new_token()
                save(sc, data)
            signed = a.get("signed") or {}
            if signed:
                st.success(f"Signed by {signed.get('name')} on {_nice_day(str(signed.get('at'))[:10])}.",
                           icon=":material/verified:")
            else:
                st.caption("Send this link to the agent on WhatsApp. They read the agreement, type their full name "
                           "and sign on their phone. Your signature is already on it. Keep the link private.")
            st.code(f"https://usegympulseai.com/?{SIGN_PARAM}={a['token']}", language=None)
            st.caption(f"Their sign-up link for gyms: usegympulseai.com/?{REF_PARAM}={pick_a}")
            day = None
            try:
                day = date.fromisoformat(a.get("since")) if a.get("since") else None
            except ValueError:
                pass
            st.download_button("Download signed agreement (PDF)" if signed else "Preview the agreement (PDF)",
                               agreement_pdf(pick_a, a, day), key="ag_doc", mime="application/pdf",
                               file_name=f"GymPulse-AI-agent-agreement-{pick_a}.pdf")

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


# ------------------------------------------------------------------ the agreement, as a branded PDF
NAVY, INK, MUTED, LINE, LIME = "#0B1220", "#111827", "#5B6473", "#D9DEE6", "#B7F34A"


def _fonts():
    import os
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        pdfmetrics.getFont("GP-Sans")
    except KeyError:
        try:
            pdfmetrics.registerFont(TTFont("GP-Sans", os.path.join(here, "assets", "fonts", "InstrumentSans-Regular.ttf")))
            pdfmetrics.registerFont(TTFont("GP-Bold", os.path.join(here, "assets", "fonts", "InstrumentSans-Bold.ttf")))
        except Exception:
            return "Helvetica", "Helvetica-Bold"
    return "GP-Sans", "GP-Bold"


def agreement_text():
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "legal", "SALES_AGENT_AGREEMENT.md")
    with open(path, encoding="utf-8") as f:
        return f.read()


def agreement_pdf(code, agent, start=None):
    """The sales agent agreement for one agent: GymPulse AI branding, the agent's details filled in, and the
    founder's name and signature already applied. The agent signs on the last page."""
    import io
    import os
    import re as _re
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (Image, KeepTogether, ListFlowable, ListItem, Paragraph, SimpleDocTemplate,
                                    Spacer, Table, TableStyle)
    import gympulse_legal as gl

    reg, bold = _fonts()
    here = os.path.dirname(os.path.abspath(__file__))
    c = colors.HexColor
    body = ParagraphStyle("b", fontName=reg, fontSize=9.6, leading=14, textColor=c(INK), spaceAfter=5)
    title = ParagraphStyle("t", parent=body, fontName=bold, fontSize=26, leading=29, textColor=c(NAVY),
                           spaceAfter=8)
    h2 = ParagraphStyle("h2", parent=body, fontName=bold, fontSize=12.5, leading=16, textColor=c(NAVY),
                        spaceBefore=12, spaceAfter=6)
    small = ParagraphStyle("s", parent=body, fontSize=7.8, leading=10.5, textColor=c(MUTED), spaceAfter=0)
    label = ParagraphStyle("lab", parent=small, fontSize=7.8)
    value = ParagraphStyle("val", parent=body, fontName=bold, fontSize=10, leading=13, spaceAfter=0)
    cell = ParagraphStyle("c", parent=body, fontSize=9, leading=12, spaceAfter=0)
    head = ParagraphStyle("h", parent=cell, fontName=bold, textColor=colors.white)

    def md(s):
        s = escape(s.replace("₦", "NGN "))
        return _re.sub(r"\*\*(.+?)\*\*", lambda m: f'<font name="{bold}">{m.group(1)}</font>', s)

    if (agent.get("signed") or {}).get("at"):
        try:
            start = date.fromisoformat(str(agent["signed"]["at"])[:10])
        except ValueError:
            pass
    start = start or gw.today_local()
    details = [("Agent", agent.get("name") or ""), ("Referral code", code),
               ("WhatsApp", agent.get("phone") or ""), ("Start date", f"{start:%-d %B %Y}"),
               ("Sign-up link", f"usegympulseai.com/?{REF_PARAM}={code}")]

    flow = [Paragraph("Sales agent agreement", title), Spacer(1, 6)]
    grid = [[Paragraph(k, label) for k, _ in details[:4]], [Paragraph(md(v), value) for _, v in details[:4]]]
    t = Table(grid, colWidths=[43.5 * mm] * 4)
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, c(LINE)), ("LINEBEFORE", (1, 0), (-1, -1), 0.6, c(LINE)),
                           ("TOPPADDING", (0, 0), (-1, 0), 7), ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    flow += [t, Spacer(1, 4), Paragraph(f"Your sign-up link: {md(details[4][1])}", small), Spacer(1, 6)]

    lines = agreement_text().split("\n")
    i, items, kind = 0, [], None

    def flush():
        nonlocal items, kind
        if items:
            flow.append(ListFlowable([ListItem(Paragraph(md(x), body), leftIndent=14) for x in items],
                                     bulletType="1" if kind == "ol" else "bullet", leftIndent=14,
                                     bulletFontName=bold if kind == "ol" else reg, bulletFontSize=9.6,
                                     bulletColor=c(NAVY), bulletDedent=14, spaceAfter=4,
                                     bulletFormat="%s." if kind == "ol" else None,
                                     start=1 if kind == "ol" else "–"))
        items, kind = [], None

    while i < len(lines):
        line = lines[i].rstrip()
        if line.startswith("# ") or not line.strip():
            flush()
        elif line.startswith("## "):
            flush()
            flow.append(Paragraph(md(line[3:]), h2))
        elif line.startswith("| "):
            flush()
            rows = []
            while i < len(lines) and lines[i].startswith("| "):
                rows.append([x.strip() for x in lines[i].strip().strip("|").split("|")])
                i += 1
            data = [[Paragraph(md(x), head) for x in rows[0]]] + [[Paragraph(md(x), cell) for x in r] for r in rows[1:]]
            tb = Table(data, colWidths=[34 * mm, 42 * mm, 49 * mm, 49 * mm], repeatRows=1)
            tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), c(NAVY)),
                                    ("LINEBELOW", (0, 1), (-1, -1), 0.5, c(LINE)),
                                    ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 7)]))
            flow += [Spacer(1, 2), tb, Spacer(1, 8)]
            continue
        elif _re.match(r"^\d+\. ", line):
            if kind != "ol":
                flush()
            kind = "ol"
            items.append(_re.sub(r"^\d+\. ", "", line))
        elif line.startswith("- "):
            if kind != "ul":
                flush()
            kind = "ul"
            items.append(line[2:])
        else:
            flush()
            flow.append(Paragraph(md(line), body))
        i += 1
    flush()

    # signatures: the founder's is applied; the agent signs by hand or on screen
    png = gl.founder_signature_png()
    sig = Image(io.BytesIO(png), width=46 * mm, height=20 * mm, kind="proportional") if png else \
        Paragraph(escape(gl.FOUNDER), ParagraphStyle("sc", parent=body, fontName="Times-BoldItalic", fontSize=22, leading=26))
    signed = agent.get("signed") or {}
    theirs = Spacer(1, 20 * mm)
    their_png = gl.data_url_png(signed.get("signature_image"))
    if their_png:
        try:
            theirs = Image(io.BytesIO(their_png), width=46 * mm, height=20 * mm, kind="proportional")
        except Exception:
            pass
    elif signed.get("name"):
        theirs = Paragraph(escape(signed["name"]), ParagraphStyle("sc2", parent=body, fontName="Times-BoldItalic",
                                                                 fontSize=22, leading=26))
    when = _nice_day(str(signed.get("at") or "")[:10]) if signed else ""
    their_cap = (f"<font name='{bold}'>{escape(signed.get('name') or '')}</font><br/>Agent<br/>"
                 f"Signed electronically on {escape(when)}" if signed else
                 "Full name, signature and date")
    sig_tbl = Table([[Paragraph("For GYMPULSE AI LTD", label), "", Paragraph("The agent", label)],
                     [sig, "", theirs],
                     [Paragraph(f"<font name='{bold}'>{escape(gl.FOUNDER)}</font><br/>{escape(gl.FOUNDER_TITLE)}<br/>"
                                f"Signed {start:%-d %B %Y}", cell), "",
                      Paragraph(their_cap, cell)]],
                    colWidths=[80 * mm, 14 * mm, 80 * mm])
    sig_tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                 ("LINEABOVE", (0, 2), (0, 2), 0.7, c(NAVY)), ("LINEABOVE", (2, 2), (2, 2), 0.7, c(NAVY))]))
    flow.append(KeepTogether([Spacer(1, 10), Paragraph("Signatures", h2), sig_tbl]))

    logo = os.path.join(here, "gympulse-logo-dark.png")

    def page(canvas, doc):
        w, h = A4
        canvas.saveState()
        canvas.setFillColor(c(NAVY))
        canvas.rect(0, h - 4 * mm, w, 4 * mm, stroke=0, fill=1)
        canvas.setFillColor(c(LIME))
        canvas.rect(0, h - 4 * mm, 38 * mm, 4 * mm, stroke=0, fill=1)
        try:
            canvas.drawImage(logo, 18 * mm, h - 20 * mm, width=36 * mm, height=12.9 * mm, mask="auto")
        except Exception:
            canvas.setFont(bold, 12)
            canvas.drawString(18 * mm, h - 15 * mm, "GymPulse AI")
        canvas.setFont(reg, 8)
        canvas.setFillColor(c(MUTED))
        canvas.drawRightString(w - 18 * mm, h - 13 * mm, f"Agent {code}")
        canvas.setStrokeColor(c(LINE))
        canvas.setLineWidth(0.6)
        canvas.line(18 * mm, 14 * mm, w - 18 * mm, 14 * mm)
        canvas.drawString(18 * mm, 9.5 * mm, "GYMPULSE AI LTD, RC 9996401, Calabar, Cross River State, Nigeria. usegympulseai.com")
        canvas.drawRightString(w - 18 * mm, 9.5 * mm, f"Page {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=27 * mm,
                      bottomMargin=20 * mm, title=f"GymPulse AI sales agent agreement, {code}",
                      author="GYMPULSE AI LTD").build(flow, onFirstPage=page, onLaterPages=page)
    return buf.getvalue()


# ------------------------------------------------------------------ the agent signs (public page, no sign-in)
def _email_signed(code, agent, pdf):
    """Email the signed agreement to the agent (if they gave an email), with a copy to GymPulse AI."""
    import base64
    import requests
    import gympulse_admin as gadm
    import gympulse_email as ge
    key = gadm._env("RESEND_API_KEY")
    if not key:
        return False
    to = [agent["email"]] if "@" in gw._text(agent.get("email")) else []
    first = gw._text(agent.get("name")).split(" ")[0] or "there"
    body = (f'<p style="margin:0 0 10px">Hi {ge.esc(first)},</p>'
            '<p style="margin:0 0 10px">Welcome to GymPulse AI. Your signed sales agent agreement is attached, '
            "signed by you and by GymPulse AI.</p>"
            + ge.details([("Agent", ge.esc(agent.get("name"))), ("Referral code", ge.esc(code)),
                          ("Your sign-up link", ge.esc(f"usegympulseai.com/?{REF_PARAM}={code}"))]))
    try:
        r = requests.post("https://api.resend.com/emails", timeout=25, headers={"Authorization": f"Bearer {key}"},
                          json={"from": gadm._env("BILLING_FROM", "GymPulse AI <billing@usegympulseai.com>"),
                                "to": to or ["emmanuel@usegympulseai.com"],
                                **({"bcc": ["emmanuel@usegympulseai.com"]} if to else {}),
                                "reply_to": "emmanuel@usegympulseai.com",
                                "subject": f"Your signed GymPulse AI agent agreement ({code})",
                                "html": ge.layout("Agreement signed", body, preheader="Your signed agreement is attached"),
                                "text": f"Hi {first},\n\nYour signed GymPulse AI sales agent agreement is attached.\n",
                                "attachments": [{"filename": f"GymPulse-AI-agent-agreement-{code}.pdf",
                                                 "content": base64.b64encode(pdf).decode()}]})
        return r.status_code < 300
    except Exception as error:
        import gympulse_monitoring as gmon
        gmon.capture(error, "agent agreement email")
        return False


def render_sign(token):
    """usegympulseai.com/?agent=TOKEN: the agent reads the agreement, adds their details and signs."""
    import gympulse_billing as gbill
    import gympulse_booking as gb
    import gympulse_legal as gl
    gb._header()
    col = gw.center("agent_sign", 600)
    with col:
        sc = gbill._service()
        data = load(sc) if sc else None
        code = next((c for c, a in ((data or {}).get("agents") or {}).items()
                     if a.get("token") and a.get("token") == gw._text(token).strip()), None)
        if not code:
            st.error("This agreement link isn't active. Ask GymPulse AI for a new one.")
            return
        agent = data["agents"][code]
        gw._md('<div class="bk-title">Your GymPulse AI agent agreement</div>'
               f'<div class="bk-sub">Referral code {gw._esc(code)}. Already signed for GymPulse AI by '
               f'{gw._esc(gl.FOUNDER)}, {gw._esc(gl.FOUNDER_TITLE)}.</div>')
        signed = agent.get("signed") or {}
        if signed:
            st.success(f"Signed by {signed.get('name')} on {_nice_day(str(signed.get('at'))[:10])}. "
                       "A copy has been sent to you and to GymPulse AI.", icon=":material/verified:")
            st.download_button("Download your signed agreement (PDF)", agreement_pdf(code, agent),
                               file_name=f"GymPulse-AI-agent-agreement-{code}.pdf", mime="application/pdf",
                               type="primary", use_container_width=True, key="as_dl")
            st.caption(f"Your sign-up link for gyms: usegympulseai.com/?{REF_PARAM}={code}")
            return

        st.markdown("**How it works:** introduce gyms, set them up during their free trial, and earn 50% of each "
                    "gym's first paid month once set-up is done, then 10% of each payment for 12 months.")
        with st.expander("Read the full agreement", icon=":material/contract:"):
            text = "\n".join(l for l in agreement_text().split("\n") if not l.startswith("# "))
            st.markdown(text)
        st.download_button("Or download it to read (PDF)", agreement_pdf(code, agent), key="as_prev",
                           file_name=f"GymPulse-AI-agent-agreement-{code}.pdf", mime="application/pdf")

        st.markdown("**Sign here**")
        st.caption("Draw your signature in the box with your finger.")
        drawn = gl.signature_pad("as_pad")
        with st.form("as_form", border=False):
            name = st.text_input("Your full legal name", value=agent.get("name") or "",
                                 placeholder="As on your ID, e.g. Babatunde Adewale Bakare")
            c1, c2 = st.columns(2)
            phone = c1.text_input("WhatsApp number", value=agent.get("phone") or "", placeholder="e.g. 0803 000 0000")
            email = c2.text_input("Email", value=agent.get("email") or "",
                                  help="We send your signed copy here.")
            typed = st.text_input("Type your full name to sign") if drawn is False else None
            agree = st.checkbox("I have read and agree to the GymPulse AI sales agent agreement. I understand I am an "
                                "independent agent, not an employee, and that commission is my only payment.")
            go = st.form_submit_button("Sign the agreement", type="primary", use_container_width=True)
        if go:
            full = " ".join(name.split())
            problems = [m for ok, m in [
                (len(full.split()) >= 2, "your full name (first and last name)"),
                (len("".join(ch for ch in phone if ch.isdigit())) >= 10, "your WhatsApp number"),
                ("@" in email and "." in email.split("@")[-1], "a valid email"),
                ((drawn is not False and drawn) or (drawn is False and " ".join((typed or "").split()).lower()
                                                     == full.lower()),
                 "your signature" + (" (type your full name exactly)" if drawn is False else " (draw it in the box)")),
                (agree, "a tick to agree")] if not ok]
            if problems:
                st.error("Please add " + ", ".join(problems) + ".")
                return
            data = load(sc)                                  # fresh copy, then save
            a = data["agents"].get(code)
            if not a or a.get("token") != agent.get("token"):
                st.error("This agreement link has changed. Ask GymPulse AI for a new one.")
                return
            if not a.get("signed"):
                a.update({"name": full, "phone": phone.strip(), "email": email.strip(),
                          "signed": {"name": full, "at": datetime.now(timezone.utc).isoformat(),
                                     "signature_image": gl.png_data_url(drawn) if drawn else None,
                                     "text_sha256": gl.fingerprint(agreement_text())}})
                save(sc, data)
                _email_signed(code, a, agreement_pdf(code, a))
            st.rerun()
