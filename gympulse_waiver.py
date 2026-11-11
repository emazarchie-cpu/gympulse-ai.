"""GymPulse AI · Membership Agreement and Waiver, signed by each member.

Every member of a gym signs the gym's Membership Agreement and Waiver (docs/legal/MEMBER_AGREEMENT.md, the
gym's and member's details filled in, plus the gym's own house rules):
  * at the front desk, straight after registering them (staff hand over the phone or tablet), or
  * through their personal signing link (usegympulseai.com/?waiver=<member's private token>), sent on
    WhatsApp: for members who joined through the sign-up link or were imported.
They answer short health questions, give an emergency contact and draw their signature. The record is kept
in member_waivers (sql/phase42_member_waivers.sql) and the signed PDF can be downloaded at any time.
"""
from datetime import datetime, timezone
from urllib.parse import quote

import pandas as pd
import streamlit as st

import gympulse_legal as glegal
import gympulse_workspaces as gw

VERSION = "1.0"
SQL_HINT = ("Membership agreements need a one-time setup: open Supabase, go to SQL Editor, paste in the file "
            "sql/phase42_member_waivers.sql and press Run.")
HEALTH = [
    ("heart", "Has a doctor ever said you have a heart condition or high blood pressure?"),
    ("chest", "Do you get chest pain, or feel faint or dizzy, during or after exercise?"),
    ("breath", "Do you have asthma or other breathing problems?"),
    ("joints", "Do you have a bone, joint, back or muscle problem that exercise could make worse?"),
    ("meds", "Are you taking medication that could affect exercise (for example for blood pressure, heart or "
             "diabetes)?"),
    ("pregnant", "Are you pregnant, or have you given birth in the last 6 months?"),
    ("other", "Is there any other reason you should not exercise without medical advice?"),
]


# ------------------------------------------------------------------ the text
def _template():
    import os
    try:
        with open(os.path.join(glegal.HERE, "docs", "legal", "MEMBER_AGREEMENT.md"), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _money(x):
    try:
        return f"₦{float(x):,.0f}" if float(x) else "–"
    except (TypeError, ValueError):
        return "–"


def _date(v):
    d = pd.to_datetime(v, errors="coerce")
    return "–" if pd.isna(d) else f"{d:%d %B %Y}"


def member_terms(client, gym_id, member):
    """Plan, fee, start and end for the agreement, from the member's record and plan."""
    plan, fee = None, None
    try:
        rows = client.table("member_activity").select("membership_type, monthly_fee").eq("member_id", member["id"]) \
            .limit(1).execute().data or []
        if rows:
            plan, fee = rows[0].get("membership_type"), rows[0].get("monthly_fee")
    except Exception:
        pass
    plan = gw._text(member.get("plan_name")) or gw._text(plan) or "–"
    paid = member.get("last_payment") or fee
    start = member.get("last_renewed_on") or member.get("member_since") or member.get("created_at")
    if member.get("hmo_provider"):
        plan, paid = f"{plan} (paid by {member['hmo_provider']})", None
    return {"plan": plan, "fee": _money(paid), "start": _date(start), "end": _date(member.get("membership_end"))}


def house_rules(client, gym_id):
    """The gym's own extra rules (Member Management -> Membership agreements), one per line."""
    try:
        g = client.table("gyms").select("owner_id").eq("id", gym_id).limit(1).execute().data
        prof = client.table("profiles").select("settings").eq("id", g[0]["owner_id"]).limit(1).execute().data
        return gw._text(dict(dict((prof[0] if prof else {}).get("settings") or {}).get("waiver") or {}).get("rules"))
    except Exception:
        return ""


def agreement_text(gym_name, member, terms, rules=""):
    contact = " · ".join(x for x in (gw._text(member.get("phone")), gw._text(member.get("email"))) if x) or "–"
    extra = "".join(f"- {r.strip().lstrip('-•').strip()}\n" for r in (rules or "").splitlines() if r.strip())
    out = _template()
    for k, v in (("GYM", gym_name), ("MEMBER", gw._text(member.get("full_name"))), ("CONTACT", contact),
                 ("PLAN", terms["plan"]), ("FEE", terms["fee"]), ("START", terms["start"]), ("END", terms["end"])):
        out = out.replace(f"[[{k}]]", gw._text(v) or "–")
    return out.replace("[[HOUSE_RULES]]\n", extra).replace("[[HOUSE_RULES]]", extra)


# ------------------------------------------------------------------ records
def latest(client, member_id):
    try:
        rows = (client.table("member_waivers").select("*").eq("member_id", member_id).eq("version", VERSION)
                .order("signed_at", desc=True).limit(1).execute().data or [])
        return rows[0] if rows else None
    except Exception:
        return None


def signed_ids(client, gym_id):
    """{member_id: signed_at} for the current version, or None when phase 42 hasn't been run."""
    try:
        rows = gw.fetch_all(client.table("member_waivers").select("member_id, signed_at").eq("gym_id", gym_id)
                            .eq("version", VERSION).order("signed_at"))
    except Exception:
        return None
    return {r["member_id"]: r["signed_at"] for r in rows}


def waiver_pdf(gym_name, text, rec):
    when = str(rec.get("signed_at") or "")[:16].replace("T", " ")
    health = dict(rec.get("health") or {})
    yes = [q for k, q in HEALTH if health.get(k)]
    block = ("MEMBER", glegal.data_url_png(rec.get("signature_image")), rec.get("signer_name"),
             f"<b>{glegal._esc(rec.get('signer_name'))}</b><br/>Member of {glegal._esc(gym_name)}<br/>"
             f"Signed electronically on {glegal._esc(when)} UTC")
    footer = [("Health questions answered yes: " + glegal._esc(" / ".join(yes))) if yes
              else "Health questions: answered no to all.",
              f"Emergency contact: {glegal._esc(rec.get('emergency_name'))} · {glegal._esc(rec.get('emergency_phone'))}",
              f"Signing record: signed {'at the front desk' if rec.get('signed_via') == 'front_desk' else 'by personal link'}"
              + (f" · IP {glegal._esc(rec.get('ip'))}" if rec.get("ip") else "")
              + f" · version {glegal._esc(rec.get('version'))} · SHA-256 of the text: {glegal._esc(rec.get('text_sha256'))}",
              "Prepared with GymPulse AI · usegympulseai.com"]
    return signed_pdf_safe(text, [block], footer, f"{gym_name} Membership Agreement and Waiver")


def signed_pdf_safe(text, blocks, footer, title):
    return glegal.signed_pdf(text, blocks, footer, title)


def link_for(member):
    return f"{gw.APP_URL}/?waiver={member.get('portal_token')}"


# ------------------------------------------------------------------ the signing form
def sign_form(client, gym_id, gym_name, member, via, key):
    """Agreement, health questions, emergency contact and a drawn signature. Saves and returns the record."""
    terms = member_terms(client, gym_id, member)
    text = agreement_text(gym_name, member, terms, house_rules(client, gym_id))
    with st.container(height=320, border=True):
        st.markdown("\n".join(l for l in text.split("\n") if not l.startswith("# ")))
    st.markdown("**Health questions**")
    health = {}
    for k, q in HEALTH:
        health[k] = st.radio(q, ["No", "Yes"], horizontal=True, key=f"{key}_h_{k}") == "Yes"
    if any(health.values()):
        st.info("Because you answered yes, please speak to a doctor before you start or increase exercise, and "
                "tell your trainer.")
    c1, c2 = st.columns(2)
    ename = c1.text_input("Emergency contact name", key=f"{key}_en")
    ephone = c2.text_input("Emergency contact phone", key=f"{key}_ep", placeholder="e.g. 0803 000 0000")
    st.markdown(f"**Signature of {gw._esc(member.get('full_name'))}**")
    drawn = glegal.signature_pad(f"{key}_pad")
    typed = None
    if drawn is False:
        typed = st.text_input("Type your full name to sign", key=f"{key}_typed")
    agree = st.checkbox("I have read and understood this Agreement and Waiver, my health answers are true, and I "
                        "agree to it.", key=f"{key}_ok")
    if not st.button("Sign the agreement", type="primary", icon=":material/draw:", key=f"{key}_go",
                     use_container_width=True):
        return None
    norm = lambda x: " ".join(gw._text(x).lower().split())
    problems = [m for ok, m in [(ename.strip(), "an emergency contact name"),
                                (len("".join(ch for ch in ephone if ch.isdigit())) >= 7, "an emergency contact phone"),
                                (bool(drawn) or (drawn is False and norm(typed) == norm(member.get("full_name"))),
                                 "your signature" + (" (type your full name exactly)" if drawn is False else
                                                     " (draw it in the box)")),
                                (agree, "to tick that you agree")] if not ok]
    if problems:
        st.error("Please add " + ", ".join(problems) + ".")
        return None
    try:
        ip = st.context.ip_address
        agent = (st.context.headers or {}).get("User-Agent")
    except Exception:
        ip = agent = None
    rec = {"gym_id": gym_id, "member_id": member["id"], "version": VERSION, "text_sha256": glegal.fingerprint(text),
           "signer_name": gw._text(member.get("full_name")), "agreement_text": text,
           "signature_image": glegal.png_data_url(drawn) if drawn else None, "health": health,
           "emergency_name": ename.strip(), "emergency_phone": ephone.strip(), "signed_via": via,
           "signed_at": datetime.now(timezone.utc).isoformat(), "ip": ip, "user_agent": (agent or "")[:300] or None}
    try:
        client.table("member_waivers").insert(rec).execute()
    except Exception as error:
        st.error(SQL_HINT if "member_waivers" in str(error) else f"Could not save the signature: {error}")
        return None
    return rec


def _download(gym_name, rec, text, key):
    import gympulse_reports as rp
    pdf = waiver_pdf(gym_name, rec.get("agreement_text") or text, rec)
    name = "".join(ch if ch.isalnum() else "-" for ch in gw._text(rec.get("signer_name"))).strip("-") or "member"
    rp.download_link("Download the signed agreement (PDF)", pdf, f"Membership-Agreement-{name}.pdf", rp.PDF, key)


# ------------------------------------------------------------------ the member's own signing page
def render_public(supabase, token):
    import gympulse_admin as gadm
    import gympulse_booking as gb
    gb._header()
    col = gw.center("waiver", 720)
    with col:
        sc = gadm.service_client()
        try:
            rows = sc.table("members").select("*").eq("portal_token", str(token)).limit(1).execute().data or [] \
                if sc else []
        except Exception:
            rows = []
        m = rows[0] if rows else None
        if not m or m.get("archived"):
            st.error("This signing link isn't valid any more. Please ask the gym for a new one.")
            return
        try:
            g = sc.table("gyms").select("business_name").eq("id", m["gym_id"]).limit(1).execute().data or [{}]
        except Exception:
            g = [{}]
        gym_name = gw._text(g[0].get("business_name"), "your gym")
        gw._md(f'<div class="bk-title">{gw._esc(gym_name)}</div>'
               f'<div class="bk-sub">Membership Agreement and Waiver for {gw._esc(m.get("full_name"))}</div>')
        done = st.session_state.get(f"wv_done_{m['id']}") or latest(sc, m["id"])
        if done:
            st.success("Thank you! Your membership agreement is signed. You don't need to sign again.",
                       icon=":material/verified:")
            text = done.get("agreement_text") or agreement_text(gym_name, m, member_terms(sc, m["gym_id"], m),
                                                                house_rules(sc, m["gym_id"]))
            _download(gym_name, done, text, "wv_pub_dl")
            return
        rec = sign_form(sc, m["gym_id"], gym_name, m, "link", "wv_pub")
        if rec:
            st.session_state[f"wv_done_{m['id']}"] = rec
            st.rerun()


# ------------------------------------------------------------------ front desk: straight after registering
def render_new_member(supabase, gym_id, member_id):
    try:
        m = (supabase.table("members").select("*").eq("id", member_id).limit(1).execute().data or [None])[0]
    except Exception:
        m = None
    if not m:
        return
    gym_name = gw._text((st.session_state.get("user_profile") or {}).get("business_name"), "our gym")
    with st.container(border=True):
        st.markdown(f"**Next: {gw._esc(m.get('full_name'))} signs the membership agreement and waiver**")
        done = st.session_state.get(f"wv_done_{member_id}") or latest(supabase, member_id)
        if done:
            st.success("Signed. It's saved on their profile.", icon=":material/verified:")
            text = done.get("agreement_text") or agreement_text(gym_name, m, member_terms(supabase, gym_id, m),
                                                                house_rules(supabase, gym_id))
            _download(gym_name, done, text, f"wv_new_dl_{member_id}")
            if st.button("Done", key=f"wv_new_close_{member_id}"):
                st.session_state.pop("mm_new_member", None)
                st.rerun()
            return
        t1, t2 = st.tabs(["Sign here now", "Send them the link"])
        with t1:
            st.caption("Hand this phone or tablet to the member to read, answer and sign.")
            rec = sign_form(supabase, gym_id, gym_name, m, "front_desk", f"wv_new_{member_id}")
            if rec:
                st.session_state[f"wv_done_{member_id}"] = rec
                st.rerun()
        with t2:
            _send_link(m, gym_name, f"wv_new_send_{member_id}")
        if st.button("Later", key=f"wv_new_later_{member_id}", type="tertiary"):
            st.session_state.pop("mm_new_member", None)
            st.rerun()


def _send_link(m, gym_name, key):
    url = link_for(m)
    msg = (f"Hi {gw._text(m.get('full_name')).split(' ')[0] or 'there'}, welcome to {gym_name}! Please read and sign "
           f"your membership agreement here (2 minutes): {url}")
    st.code(url, language=None, wrap_lines=True)
    digits = gw.whatsapp_digits(m.get("phone"))
    if digits:
        st.link_button("Send on WhatsApp", f"https://wa.me/{digits}?text={quote(msg)}", icon=":material/chat:",
                       use_container_width=True)
    else:
        st.caption("No phone number on their profile: copy the link above and send it to them.")


# ------------------------------------------------------------------ owner / staff overview (Member Management)
def render_overview(supabase, gym_id):
    signed = signed_ids(supabase, gym_id)
    if signed is None:
        st.info(SQL_HINT)
        return
    members, _ = gw.fetch_members(supabase, gym_id, archived=False, include_photo=False)
    if members.empty:
        st.caption("No members yet.")
        return
    total, n = len(members), sum(1 for i in members["id"] if i in signed)
    gw.kpi_row([("Signed", f"{n:,}", "lime", "agreement and waiver"),
                ("Not signed yet", f"{total - n:,}", "amber" if total - n else "grey", "send them their link")])
    gym_name = gw._text((st.session_state.get("user_profile") or {}).get("business_name"), "our gym")
    if st.session_state.get("role") != "staff":
        with st.expander("Your house rules (added to every agreement)", icon=":material/rule:"):
            prof = st.session_state.get("user_profile") or {}
            current = gw._text(dict(dict(prof.get("settings") or {}).get("waiver") or {}).get("rules"))
            rules = st.text_area("One rule per line", value=current, height=140, key="wv_rules",
                                 placeholder="e.g. Guests are welcome on Saturdays only\nNo training without a towel")
            if st.button("Save house rules", key="wv_rules_save", type="primary"):
                s = {**dict(prof.get("settings") or {}), "waiver": {**dict(dict(prof.get("settings") or {})
                                                                         .get("waiver") or {}), "rules": rules.strip()}}
                try:
                    supabase.table("profiles").update({"settings": s}).eq("id", prof.get("id") or
                                                                        (st.session_state.get("auth_user") or {}).get("id")).execute()
                    prof["settings"] = s
                    st.success("Saved. New agreements include your rules.")
                except Exception as error:
                    st.error(f"Could not save: {error}")
    todo = members[~members["id"].isin(list(signed))]
    if len(todo):
        names = dict(zip(todo["id"], todo["full_name"]))
        pick = st.selectbox("Send the signing link to", list(names), format_func=names.get, index=None,
                            placeholder="Choose a member who hasn't signed", key="wv_pick")
        if pick:
            _send_link(todo[todo["id"] == pick].iloc[0].to_dict(), gym_name, "wv_pick_send")
    done = members[members["id"].isin(list(signed))]
    if len(done):
        names = dict(zip(done["id"], done["full_name"]))
        pick = st.selectbox("Download a signed agreement", list(names), format_func=names.get, index=None,
                            placeholder="Choose a member", key="wv_dl_pick")
        if pick:
            rec = latest(supabase, pick)
            m = done[done["id"] == pick].iloc[0].to_dict()
            if rec:
                text = agreement_text(gym_name, m, member_terms(supabase, gym_id, m), house_rules(supabase, gym_id))
                st.caption(f"Signed {_date(rec.get('signed_at'))}"
                           + (" at the front desk." if rec.get("signed_via") == "front_desk" else " by personal link."))
                _download(gym_name, rec, text, "wv_dl_btn")
