"""GymPulse AI · Terms, Privacy Policy and Data Processing Agreement.

The documents live in docs/legal/*.md, so the app always shows the same text
the lawyer reviewed. Each gym owner accepts them once per version. New owners
accept at sign-up; existing owners see a short banner until they accept. The
acceptance (version, time, email) is saved in their profile settings.
"""
import os
from datetime import datetime, timezone

import streamlit as st

LEGAL_VERSION = "1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = {"terms": "TERMS_OF_SERVICE.md", "privacy": "PRIVACY_POLICY.md", "dpa": "DATA_PROCESSING_AGREEMENT.md",
        "subscription": "SUBSCRIPTION_AGREEMENT.md"}
TITLES = {"terms": "Terms of Service", "privacy": "Privacy Policy", "dpa": "Data Processing Agreement",
          "subscription": "Subscription Agreement"}
SUBSCRIPTION_VERSION = "1.0"
SIGNER_ROLES = ["Owner", "Director", "Manager", "Partner", "Other authorised person"]
FOUNDER, FOUNDER_TITLE = "Emmanuel Archibong", "Founder"
# The Founder's signature, applied to every Subscription Agreement (transparent PNG). Until it's added, the
# name is shown in a signature-style font instead.
FOUNDER_SIGNATURE = os.path.join(HERE, "assets", "founder-signature.png")

CONSENT_TEXT = ("I have my members' permission to store their details in GymPulse AI and to email or message them, "
                "and I'll tell my members that my gym uses GymPulse AI.")


COMPANY = "GYMPULSE AI LTD · RC 9996401 · Calabar, Cross River State, Nigeria"


def read(kind):
    try:
        with open(os.path.join(HERE, "docs", "legal", DOCS[kind]), encoding="utf-8") as f:
            text = f.read()
        lines = text.split("\n")
        body = "\n".join(l for l in lines if not l.startswith("# "))     # the dialog has its own title
        return body + f"\n\n---\n*{COMPANY}*"
    except Exception:
        return f"The {TITLES[kind]} is being updated. Email hello@usegympulseai.com for a copy."


@st.dialog("Terms of Service", width="large")
def show_terms():
    st.markdown(read("terms"))


@st.dialog("Privacy Policy", width="large")
def show_privacy():
    st.markdown(read("privacy"))


@st.dialog("Data Processing Agreement", width="large")
def show_dpa():
    st.markdown(read("dpa"))


def founder_signature_png():
    try:
        with open(FOUNDER_SIGNATURE, "rb") as f:
            return f.read()
    except OSError:
        return None


def render_founder_signature():
    """GymPulse AI's signature block, as it appears on every agreement."""
    png = founder_signature_png()
    if png:
        st.image(png, width=220)
    else:
        st.markdown('<div style="font:italic 30px/1.2 \'Brush Script MT\',\'Segoe Script\',cursive">'
                    f'{FOUNDER}</div>', unsafe_allow_html=True)
    st.caption(f"{FOUNDER}, {FOUNDER_TITLE}, for and on behalf of GYMPULSE AI LTD (applied electronically)")


@st.dialog("Subscription Agreement", width="large")
def show_subscription():
    st.markdown(read("subscription"))
    render_founder_signature()


def latest_signature(supabase, gym_id, profile=None):
    """The gym's signature of the current Subscription Agreement version, or None (sign once)."""
    try:
        rows = (supabase.table("agreement_signatures").select("*").eq("gym_id", gym_id)
                .eq("document", "subscription").eq("version", SUBSCRIPTION_VERSION)
                .order("signed_at", desc=True).limit(1).execute().data or [])
        if rows:
            return rows[0]
    except Exception:
        pass
    for r in reversed(list(dict((profile or {}).get("settings") or {}).get("agreements") or [])):
        if r.get("version") == SUBSCRIPTION_VERSION and str(r.get("gym_id")) == str(gym_id):
            return r
    return None


def agreement_pdf(sig, text=None):
    """The signed agreement as a PDF: the full text, then both signatures and the signing record."""
    import io
    import re as _re
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape
    text = text if text is not None else subscription_text()
    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=9.5, leading=13.5, spaceAfter=5)
    h1 = ParagraphStyle("h1", parent=body, fontName="Helvetica-Bold", fontSize=17, leading=21, spaceAfter=10)
    h2 = ParagraphStyle("h2", parent=body, fontName="Helvetica-Bold", fontSize=11, leading=15, spaceBefore=8)
    small = ParagraphStyle("s", parent=body, fontSize=7.5, leading=10, textColor=colors.HexColor("#6B7280"))
    script = ParagraphStyle("sig", parent=body, fontName="Times-BoldItalic", fontSize=22, leading=26)

    def md(line):
        line = escape(line)
        return _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
    flow = []
    for line in text.split("\n"):
        if line.startswith("# "):
            flow.append(Paragraph(md(line[2:]), h1))
        elif line.startswith("## "):
            flow.append(Paragraph(md(line[3:]), h2))
        elif line.startswith("- "):
            flow.append(Paragraph("• " + md(line[2:]), body))
        elif line.strip():
            flow.append(Paragraph(md(line), body))
    flow.append(Spacer(1, 10))
    png = founder_signature_png()
    ours = [Image(io.BytesIO(png), width=50 * mm, height=18 * mm, kind="proportional") if png
            else Paragraph(FOUNDER, script),
            Paragraph(f"<b>{FOUNDER}</b>, {FOUNDER_TITLE}<br/>for and on behalf of GYMPULSE AI LTD<br/>"
                      "Signature applied electronically", body)]
    when = str(sig.get("signed_at") or "")[:16].replace("T", " ")
    theirs = [Paragraph(escape(gw_text(sig.get("signer_name"))), script),
              Paragraph(f"<b>{escape(gw_text(sig.get('signer_name')))}</b>, {escape(gw_text(sig.get('signer_role')))}"
                        f"<br/>for and on behalf of {escape(gw_text(sig.get('business_name')))}<br/>"
                        f"Signed electronically on {escape(when)} UTC", body)]
    t = Table([[Paragraph("<b>FOR GYMPULSE AI LTD</b>", body), Paragraph("<b>FOR THE SUBSCRIBER</b>", body)],
               [ours[0], theirs[0]], [ours[1], theirs[1]]], colWidths=[85 * mm, 85 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                           ("LINEABOVE", (0, 2), (-1, 2), 0.6, colors.HexColor("#111827")),
                           ("TOPPADDING", (0, 0), (-1, -1), 4)]))
    flow.append(t)
    flow.append(Spacer(1, 10))
    rec = (f"Signing record: {escape(gw_text(sig.get('signer_email')))}"
           + (f" · IP {escape(gw_text(sig.get('ip')))}" if sig.get("ip") else "")
           + f" · Plan at signing: {escape(gw_text(sig.get('plan')))}"
           + f" · Agreement version {escape(gw_text(sig.get('version') or SUBSCRIPTION_VERSION))}"
           + f" · SHA-256 of the text: {escape(gw_text(sig.get('text_sha256')))}")
    flow.append(Paragraph(rec, small))
    flow.append(Paragraph(escape(COMPANY), small))
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                      bottomMargin=16 * mm, title="GymPulse AI Subscription Agreement").build(flow)
    return buf.getvalue()


def gw_text(v):
    return "" if v is None else str(v)


def subscription_text():
    """The exact agreement text a gym signs (file contents), for the fingerprint and the emailed copy."""
    try:
        with open(os.path.join(HERE, "docs", "legal", DOCS["subscription"]), encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def fingerprint(text):
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def acceptance(email):
    return {"version": LEGAL_VERSION, "accepted_at": datetime.now(timezone.utc).isoformat(), "email": email,
            "members_consent": True}


def accepted(profile):
    s = dict((profile or {}).get("settings") or {})
    return (s.get("legal") or {}).get("version") == LEGAL_VERSION


def render_acceptance_banner(supabase, owner_id):
    """For owners who signed up before this version: accept once, then it disappears."""
    profile = st.session_state.get("user_profile") or {}
    if accepted(profile):
        return
    with st.container(border=True):
        st.markdown("**Please review our updated terms.** To keep using GymPulse AI under the Nigeria Data "
                    "Protection Act, we need you to accept these once.")
        c1, c2, c3 = st.columns(3)
        if c1.button("Terms of Service", key="legal_b_terms", use_container_width=True):
            show_terms()
        if c2.button("Privacy Policy", key="legal_b_privacy", use_container_width=True):
            show_privacy()
        if c3.button("Data Processing Agreement", key="legal_b_dpa", use_container_width=True):
            show_dpa()
        a = st.checkbox("I agree to the Terms of Service, Privacy Policy and Data Processing Agreement",
                        key="legal_b_agree")
        b = st.checkbox(CONSENT_TEXT, key="legal_b_consent")
        if st.button("Accept", type="primary", key="legal_b_accept", disabled=not (a and b)):
            email = (st.session_state.get("auth_user") or {}).get("email", "")
            s = {**dict(profile.get("settings") or {}), "legal": acceptance(email)}
            try:
                supabase.table("profiles").update({"settings": s}).eq("id", owner_id).execute()
                profile["settings"] = s
                st.session_state["user_profile"] = profile
                st.rerun()
            except Exception as error:
                st.error(f"Could not save: {error}")
