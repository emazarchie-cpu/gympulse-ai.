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


# ------------------------------------------------------------------ the signature pad (draw with finger or mouse)
_PAD_HTML = """
<div class="gp-sig">
  <canvas class="gp-sig-canvas" aria-label="Signature box: draw your signature"></canvas>
  <div class="gp-sig-line"></div>
  <div class="gp-sig-bar"><span class="gp-sig-hint">Sign above with your finger or mouse</span>
    <button type="button" class="gp-sig-clear">Clear</button></div>
</div>
"""
_PAD_CSS = """
.gp-sig { position: relative; }
.gp-sig-canvas { width: 100%; height: 170px; display: block; background: #ffffff; border-radius: 12px;
  border: 1.5px dashed rgba(120,130,150,.6); touch-action: none; cursor: crosshair; }
.gp-sig-line { position: absolute; left: 22px; right: 22px; top: 128px; border-top: 1px solid #c9ced8;
  pointer-events: none; }
.gp-sig-bar { display: flex; justify-content: space-between; align-items: center; margin-top: 6px;
  font-size: 13px; color: var(--st-text-color, #8a93a6); opacity: .85; }
.gp-sig-clear { border: 1px solid rgba(120,130,150,.5); background: transparent; color: inherit;
  border-radius: 999px; padding: 4px 14px; font-size: 13px; cursor: pointer; }
"""
_PAD_JS = """
export default function(component) {
  const { parentElement, setStateValue } = component;
  const canvas = parentElement.querySelector('.gp-sig-canvas');
  const clear = parentElement.querySelector('.gp-sig-clear');
  const hint = parentElement.querySelector('.gp-sig-hint');
  const ctx = canvas.getContext('2d');
  let drawing = false, points = 0, last = null;
  function size() {
    const r = canvas.getBoundingClientRect(), d = window.devicePixelRatio || 1;
    const keep = points ? canvas.toDataURL() : null;
    canvas.width = Math.round(r.width * d); canvas.height = Math.round(r.height * d);
    ctx.setTransform(d, 0, 0, d, 0, 0);
    ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.strokeStyle = '#161c46'; ctx.lineWidth = 2.6;
    if (keep) { const im = new Image(); im.onload = () => ctx.drawImage(im, 0, 0, r.width, r.height); im.src = keep; }
  }
  function pos(e) { const r = canvas.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; }
  canvas.addEventListener('pointerdown', (e) => {
    e.preventDefault(); canvas.setPointerCapture(e.pointerId); drawing = true; last = pos(e);
    ctx.beginPath(); ctx.arc(last.x, last.y, 1.2, 0, Math.PI * 2); ctx.fillStyle = '#161c46'; ctx.fill();
  });
  canvas.addEventListener('pointermove', (e) => {
    if (!drawing) return; e.preventDefault();
    const p = pos(e); ctx.beginPath(); ctx.moveTo(last.x, last.y); ctx.lineTo(p.x, p.y); ctx.stroke();
    last = p; points += 1;
  });
  function end() {
    if (!drawing) return; drawing = false;
    if (points >= 12) { hint.textContent = 'Signed. Tap Clear to sign again.'; setStateValue('signature', canvas.toDataURL('image/png')); }
  }
  canvas.addEventListener('pointerup', end); canvas.addEventListener('pointercancel', end);
  canvas.addEventListener('pointerleave', end);
  clear.addEventListener('click', () => {
    const r = canvas.getBoundingClientRect(); ctx.clearRect(0, 0, r.width, r.height); points = 0;
    hint.textContent = 'Sign above with your finger or mouse'; setStateValue('signature', null);
  });
  size(); window.addEventListener('resize', size);
  return () => window.removeEventListener('resize', size);
}
"""
try:
    _SIGN_PAD = st.components.v2.component("gp_signature_pad", html=_PAD_HTML, css=_PAD_CSS, js=_PAD_JS)
except Exception:                                   # an older Streamlit without two-way components
    _SIGN_PAD = None


def signature_pad(key):
    """A box to draw a signature in. Returns the drawing as PNG bytes, None when empty, or False when the
    pad isn't available (then the typed signature is used instead)."""
    if _SIGN_PAD is None:
        return False
    try:
        res = _SIGN_PAD(key=key, on_signature_change=lambda: None)
    except Exception:
        return False
    url = getattr(res, "signature", None) if res is not None else None
    if not url or not str(url).startswith("data:image/png;base64,"):
        return None
    import base64
    try:
        png = base64.b64decode(str(url).split(",", 1)[1])
    except Exception:
        return None
    if png[:8] != b"\x89PNG\r\n\x1a\n" or len(png) > 600_000:
        return None
    return _trim(png)


def _trim(png):
    """Cut the empty space around a drawn signature, so it prints at a good size."""
    try:
        import io
        from PIL import Image
        im = Image.open(io.BytesIO(png)).convert("RGBA")
        box = im.getchannel("A").getbbox()
        if not box:
            return None
        pad = 12
        box = (max(box[0] - pad, 0), max(box[1] - pad, 0), min(box[2] + pad, im.width), min(box[3] + pad, im.height))
        out = io.BytesIO()
        im.crop(box).save(out, "PNG", optimize=True)
        return out.getvalue()
    except Exception:
        return png


def png_data_url(png):
    import base64
    return "data:image/png;base64," + base64.b64encode(png).decode()


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
    """The signed Subscription Agreement as a PDF: the full text, both signatures and the signing record."""
    png = founder_signature_png()
    ours = ("FOR GYMPULSE AI LTD", png, FOUNDER,
            f"<b>{FOUNDER}</b>, {FOUNDER_TITLE}<br/>for and on behalf of GYMPULSE AI LTD<br/>"
            "Signature applied electronically")
    when = str(sig.get("signed_at") or "")[:16].replace("T", " ")
    theirs = ("FOR THE SUBSCRIBER", data_url_png(sig.get("signature_image")), gw_text(sig.get("signer_name")),
              f"<b>{_esc(sig.get('signer_name'))}</b>, {_esc(sig.get('signer_role'))}<br/>"
              f"for and on behalf of {_esc(sig.get('business_name'))}<br/>Signed electronically on {_esc(when)} UTC")
    rec = (f"Signing record: {_esc(sig.get('signer_email'))}"
           + (f" · IP {_esc(sig.get('ip'))}" if sig.get("ip") else "")
           + f" · Plan at signing: {_esc(sig.get('plan'))}"
           + f" · Agreement version {_esc(sig.get('version') or SUBSCRIPTION_VERSION)}"
           + f" · SHA-256 of the text: {_esc(sig.get('text_sha256'))}")
    return signed_pdf(text if text is not None else subscription_text(), [ours, theirs], [rec, _esc(COMPANY)],
                      "GymPulse AI Subscription Agreement")


def _esc(v):
    from xml.sax.saxutils import escape
    return escape(gw_text(v))


def data_url_png(url):
    if str(url or "").startswith("data:image/png;base64,"):
        import base64
        try:
            return base64.b64decode(str(url).split(",", 1)[1])
        except Exception:
            return None
    return None


def signed_pdf(text, blocks, footer, title):
    """A signed document as a PDF: markdown-ish text (headings, bold, bullets), then signature blocks side by
    side. blocks: [(heading, signature PNG bytes or None, name shown in a signature font when no PNG,
    caption HTML)]. footer: small lines (already escaped)."""
    import io
    import re as _re
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape
    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=9.5, leading=13.5, spaceAfter=5)
    h1 = ParagraphStyle("h1", parent=body, fontName="Helvetica-Bold", fontSize=17, leading=21, spaceAfter=10)
    h2 = ParagraphStyle("h2", parent=body, fontName="Helvetica-Bold", fontSize=11, leading=15, spaceBefore=8)
    small = ParagraphStyle("s", parent=body, fontSize=7.5, leading=10, textColor=colors.HexColor("#6B7280"))
    script = ParagraphStyle("sig", parent=body, fontName="Times-BoldItalic", fontSize=22, leading=26)

    def md(line):                                    # PDF fonts have no naira sign: NGN, like receipts
        return _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escape(line.replace("₦", "NGN ")))
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
    heads, sigs, caps = [], [], []
    for head, png, name, cap in blocks:
        heads.append(Paragraph(f"<b>{escape(head)}</b>", body))
        img = None
        if png:
            try:
                img = Image(io.BytesIO(png), width=50 * mm, height=18 * mm, kind="proportional")
            except Exception:
                img = None
        sigs.append(img or Paragraph(escape(name or ""), script))
        caps.append(Paragraph(cap, body))
    width = 170 * mm / max(len(blocks), 1)
    t = Table([heads, sigs, caps], colWidths=[width] * len(blocks))
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                           ("LINEABOVE", (0, 2), (-1, 2), 0.6, colors.HexColor("#111827")),
                           ("TOPPADDING", (0, 0), (-1, -1), 4)]))
    flow.append(t)
    flow.append(Spacer(1, 10))
    for line in footer:
        flow.append(Paragraph(line.replace("₦", "NGN "), small))
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                      bottomMargin=16 * mm, title=title).build(flow)
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
