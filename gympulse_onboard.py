"""GymPulse AI · sign up by booking a demo; the app opens after set-up.

New owners sign up and pick a demo time in the same form. Until the founder (or an agent) has shown them
around and set the gym up, signing in shows "Your demo is booked" instead of the app. In Admin -> Gyms the
founder taps "Set-up done", which opens the app and starts the 30 free days from that day.

* The demo is booked through the existing demo booking (gympulse_booking, book_demo).
* The owner's account carries user_metadata demo_first=True and demo_at (ISO time).
* Set-up is recorded in platform_settings under "gym_setup" ({"gyms": {gym_id: {"done_on", "by"}}}), which gyms
  can't read or change. Owners who signed up before this existed are never held back (no demo_first).
"""
from datetime import datetime, timedelta, timezone

import streamlit as st

import gympulse_workspaces as gw

KEY = "gym_setup"
DAYS_OFFERED = 10


# ------------------------------------------------------------------ demo times for the sign-up form
def slot_options(supabase):
    """Free demo times over the next open days as one flat list (None when booking isn't set up)."""
    import gympulse_booking as gb
    cfg = gb.config()
    avail = gb.bookable(supabase, cfg)
    if avail is None:
        return None, cfg
    out = []
    for day in list(avail)[:DAYS_OFFERED]:
        out += avail[day]
    return out, cfg


def slot_label(s):
    today = datetime.now(gw.APP_TZ).date()
    day = ("Today" if s.date() == today else "Tomorrow" if s.date() == today + timedelta(days=1)
           else f"{s:%a %-d %b}")
    return f"{day}, {s:%-I:%M %p}"


def book(supabase, cfg, name, email, phone, gym, start, notes="", members=""):
    """Book the demo. Returns (booking dict or None, error message or None)."""
    import gympulse_booking as gb
    import uuid
    try:
        rows = supabase.rpc("book_demo", {
            "p_name": name, "p_email": email, "p_phone": phone, "p_gym": gym, "p_members": members or "",
            "p_notes": ("Signed up for an account (set-up demo)\n" + notes).strip(),
            "p_starts_at": start.astimezone(timezone.utc).isoformat(), "p_duration": cfg["slot"]}).execute().data or []
    except Exception as error:
        msg = str(error)
        if "slot_taken" in msg or "bad_time" in msg:
            return None, "Someone just booked that time. Please pick another."
        if "too_many" in msg:
            return None, "You already have a demo booked. Check your email for the details."
        if "bad_email" in msg:
            return None, "Please check your email address."
        return None, "We couldn't book the demo right now. Please try again in a minute."
    row = rows[0] if rows else {}
    token = row.get("cancel_token") or str(uuid.uuid4())
    b = {"id": row.get("booking_id") or token, "name": name, "email": email.lower(), "phone": phone, "gym": gym,
         "members": members or "", "notes": notes, "start": start, "cancel_url": f"{gw.APP_URL}/?demo_cancel={token}"}
    try:
        b["emailed"] = gb.send_confirmations(b, cfg)
    except Exception:
        b["emailed"] = False
    return b, None


# ------------------------------------------------------------------ set-up records (server side)
def _service():
    import gympulse_billing as gbill
    return gbill._service()


def setup_done_all(sc):
    try:
        rows = sc.table("platform_settings").select("value").eq("key", KEY).limit(1).execute().data
        return dict((rows[0]["value"] or {}).get("gyms") or {}) if rows else {}
    except Exception:
        return {}


def mark_done(sc, gym_id, by="admin", trial_days=30):
    """Open the app for this gym and start its free days from today."""
    import gympulse_billing as gbill
    done = setup_done_all(sc)
    done[str(gym_id)] = {"done_on": gw.today_local().isoformat(), "by": by}
    sc.table("platform_settings").upsert({"key": KEY, "value": {"gyms": done},
                                          "updated_at": datetime.now(timezone.utc).isoformat()},
                                         on_conflict="key").execute()
    gbill.admin_set(sc, gym_id, status="trial",
                    trial_ends_on=(gw.today_local() + timedelta(days=trial_days - 1)).isoformat())


def _user_meta():
    """The signed-in owner's user_metadata, read once per session with the server key."""
    hit = st.session_state.get("_onb_meta")
    if hit is not None:
        return hit
    meta = {}
    uid = (st.session_state.get("auth_user") or {}).get("id")
    sc = _service()
    if uid and sc:
        try:
            user = getattr(sc.auth.admin.get_user_by_id(uid), "user", None)
            meta = dict(getattr(user, "user_metadata", None) or {})
        except Exception:
            meta = {}
    st.session_state["_onb_meta"] = meta
    return meta


def waiting(gym_id):
    """True while this owner signed up through a demo and their gym hasn't been set up yet."""
    if not gym_id:
        return False
    meta = _user_meta()
    if not meta.get("demo_first"):
        return False
    sc = _service()
    if sc is None:
        return False                                   # never lock anyone out because a key is missing
    return str(gym_id) not in setup_done_all(sc)


def render_waiting(log_out=None):
    meta = _user_meta()
    first = (gw._text(meta.get("full_name")).split() or ["there"])[0]
    when = None
    try:
        when = datetime.fromisoformat(str(meta.get("demo_at"))).astimezone(gw.APP_TZ)
    except Exception:
        pass
    import gympulse_booking as gb
    meet = gb.config().get("meet")
    col = gw.center("onb_wait", 620)
    with col:
        gw._md('<div class="onb-eyebrow">Welcome to GymPulse AI</div>'
               f'<div class="onb-title">Your demo is booked, {gw._esc(first)}.</div>'
               + (f'<div class="onb-when">{when:%A %-d %B} at {when:%-I:%M %p}, Lagos time</div>' if when else "")
               + '<div class="onb-sub">On the call we show you around and set up your gym together: your members, '
                 'your check-ins, and who to call first. Your 30 free days start then, so you don\'t lose any of '
                 'them.</div>'
               '<ol class="onb-steps"><li><b>Before the call:</b> have your member list ready, from Excel, '
               'GymMaster or your register.</li><li><b>On the call:</b> we load it together and record your '
               'first check-ins.</li><li><b>After the call:</b> the app opens here, and your 30 free days start.</li>'
               '</ol>')
        c1, c2 = st.columns(2)
        if meet:
            c1.link_button("Join the call (Google Meet)", meet, use_container_width=True, type="primary")
        wa = ""
        try:
            import gympulse_billing as gbill
            wa = gw.whatsapp_digits(gbill.pricing(_service()).get("contact_whatsapp"))
        except Exception:
            wa = ""
        msg = "Hi%20GymPulse%20AI%2C%20I%27d%20like%20to%20change%20my%20demo%20time."
        c2.link_button("Change the time", f"https://wa.me/{wa}?text={msg}" if len(wa) >= 10 else
                       "mailto:emmanuel@usegympulseai.com?subject=Change%20my%20demo%20time", use_container_width=True)
        st.caption("The confirmation email has your calendar invite. Questions: emmanuel@usegympulseai.com")
        if log_out is not None:
            st.button("Log out", on_click=log_out, type="tertiary", key="onb_logout")
    gw._md("""<style>
.onb-eyebrow{color:var(--gp-muted,#8A96AB);font-size:14px;margin:28px 0 6px}
.onb-title{font-family:'Instrument Sans',sans-serif;font-weight:500;letter-spacing:-0.035em;font-size:clamp(30px,5vw,44px);
 line-height:1.08;color:var(--gp-text,#F4F6FA)}
.onb-when{margin-top:10px;font-size:17px;color:#B7F34A;font-weight:600}
.onb-sub{margin-top:14px;color:var(--gp-muted,#AAB4C3);font-size:15px;line-height:1.6}
.onb-steps{margin:18px 0 18px 18px;padding:0;color:var(--gp-text,#E6EAF0);font-size:14.5px;line-height:1.6}
.onb-steps li{margin:0 0 8px}
html body .stApp [data-testid="stBaseLinkButton-primary"], html body .stApp [data-testid="stBaseLinkButton-primary"] *{
 color:#0B1220 !important;font-weight:700 !important}
</style>""")


# ------------------------------------------------------------------ admin
def render_admin(sc, gyms, audit):
    """Admin -> Gyms: owners who booked a demo at sign-up and are waiting to be set up."""
    done = setup_done_all(sc)
    wait = [g for g in gyms if g.get("demo_first") and str(g["gym"]["id"]) not in done]
    if not wait:
        return
    st.markdown(f"**Waiting for set-up** ({len(wait)})")
    st.caption("These owners signed up and booked a demo. They see \"Your demo is booked\" until you set them up. "
               "After the call, tap Set-up done: the app opens for them and their 30 free days start today.")

    def when(g):
        try:
            return datetime.fromisoformat(str(g.get("demo_at"))).astimezone(gw.APP_TZ)
        except Exception:
            return None
    wait.sort(key=lambda g: (when(g) is None, when(g) or datetime.max.replace(tzinfo=timezone.utc)))
    gw.table([{"Demo": f"{when(g):%a %-d %b, %-I:%M %p}" if when(g) else "–", "Gym": g["name"],
               "Owner": g["owner"] or "–", "WhatsApp": g.get("phone") or g.get("signup_phone") or "–",
               "Members": (g.get("onboarding") or {}).get("members") or "–",
               "Uses today": ", ".join((g.get("onboarding") or {}).get("software") or []) or "–",
               "Check-ins": (g.get("onboarding") or {}).get("checkins") or "–",
               "Main worry": (g.get("onboarding") or {}).get("worry") or "–"} for g in wait])
    with st.expander("Their answers in full"):
        for g in wait:
            a = g.get("onboarding") or {}
            st.markdown(f"**{g['name']}** ({g['owner'] or 'owner'}, {g['email']})")
            st.text(answers_text(a) or "No answers (signed up before the questions existed).")
    names = {str(g["gym"]["id"]): g["name"] for g in wait}
    with st.form("onb_done"):
        c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
        gid = c1.selectbox("Gym", list(names), format_func=names.get, key="onb_gym")
        go = c2.form_submit_button("Set-up done: start their 30 days", type="primary", use_container_width=True)
    if go:
        mark_done(sc, gid)
        g = next(x for x in wait if str(x["gym"]["id"]) == gid)
        audit(sc, "setup_done", g, {})
        st.session_state["adm_flash"] = f"{names[gid]} is set up. The app is open and their 30 free days start today."
        st.rerun()


# ------------------------------------------------------------------ the "Get started" page (?start=1)
START_PARAM = "start"
MEMBERS = ["Under 100", "100 to 300", "300 to 700", "700 to 1,500", "Over 1,500"]
BRANCHES = ["One gym", "2 to 3 branches", "4 or more"]
SOFTWARE = ["GymMaster", "Excel or Google Sheets", "Paper register", "Another app", "Nothing yet"]
CHECKINS = ["Front desk writes it down", "QR code or card scan", "In our gym software", "We don't record visits"]
WORRIES = ["Members stop coming", "Late or missed renewals", "Too much admin", "Getting new members",
           "Something else"]


def answers_text(a):
    """The owner's answers as short lines, for the booking email and Admin."""
    rows = [("Area", a.get("area")), ("Members", a.get("members")), ("Branches", a.get("branches")),
            ("Uses today", ", ".join(a.get("software") or [])), ("Check-ins", a.get("checkins")),
            ("Main worry", a.get("worry")), ("Notes", a.get("notes"))]
    return "\n".join(f"{k}: {v}" for k, v in rows if v)


def render_start(supabase):
    """usegympulseai.com/?start=1: create the account and book the set-up demo, with a few questions that
    prepare the founder for the call."""
    import gympulse_agents as gag
    import gympulse_booking as gb
    import gympulse_legal as gl
    gb._header()
    col = gw.center("start", 640)
    with col:
        done = st.session_state.get("start_done")
        if done:
            gw._md('<div class="st-eyebrow">You\'re in</div>'
                   f'<div class="st-title">Your demo is booked, {gw._esc(done["first"])}.</div>'
                   + (f'<div class="st-when">{gw._esc(done["when"])}, Lagos time</div>' if done.get("when") else "")
                   + '<div class="st-sub">We\'ve emailed you the details. Open the confirmation link in that email '
                     '(check spam), then sign in. On the call we set up your gym together, and your 30 free days '
                     'start then.</div>')
            st.link_button("Go to sign in", "./", type="primary", use_container_width=True)
            return
        gw._md('<div class="st-eyebrow">Get started</div>'
               '<div class="st-title">Book your demo</div>'
               '<div class="st-sub">A 15-minute call to show you around and set up your gym together. Your 30 free '
               'days start after the call. A few quick questions first, so we can make the call about your gym.</div>')
        slots, cfg = slot_options(supabase)
        with st.form("start_form", border=False):
            gw._md('<div class="st-sec st-first">You</div>')
            name = st.text_input("Full name")
            c1, c2 = st.columns(2)
            email = c1.text_input("Email")
            phone = c2.text_input("WhatsApp number", placeholder="e.g. 0803 000 0000")
            c3, c4 = st.columns(2)
            pw = c3.text_input("Create a password", type="password", help="At least 8 characters.")
            pw2 = c4.text_input("Confirm password", type="password")

            gw._md('<div class="st-sec">Your gym</div>')
            c5, c6 = st.columns(2)
            gym = c5.text_input("Gym name", placeholder="Your gym's name")
            area = c6.text_input("Area and city", placeholder="e.g. Lekki, Lagos")
            c7, c8 = st.columns(2)
            members = c7.selectbox("How many members?", MEMBERS, index=None, placeholder="Choose")
            branches = c8.selectbox("Branches", BRANCHES, index=0)
            software = st.multiselect("What do you use to manage members today?", SOFTWARE, placeholder="Choose any")
            checkins = st.selectbox("How do you record visits now?", CHECKINS, index=None, placeholder="Choose")
            worry = st.selectbox("What worries you most?", WORRIES, index=None, placeholder="Choose (optional)")

            gw._md('<div class="st-sec">Your demo</div>')
            pick = st.selectbox("Pick a time (Lagos time)", slots or [], index=None, format_func=slot_label,
                                placeholder="Choose a time" if slots else "We'll WhatsApp you to pick a time")
            notes = st.text_input("Anything else we should know? (optional)",
                                  placeholder="e.g. we're opening a second branch in January")
            ref = st.text_input("Referral code (optional)", value=st.session_state.get("ref_code", ""),
                                help="If someone from GymPulse AI introduced you, enter their code.")
            agree = st.checkbox("I agree to the Terms of Service, Privacy Policy and Data Processing Agreement")
            consent = st.checkbox(gl.CONSENT_TEXT)
            go = st.form_submit_button("Book my demo", type="primary", use_container_width=True)
        st.caption("Already have an account? Sign in on the main page.")
        _style()
        if not go:
            return
        full = " ".join(name.split())
        problems = [m for ok, m in [
            (len(full.split()) >= 2, "your full name"),
            ("@" in email and "." in email.split("@")[-1], "a valid email"),
            (len(gw.whatsapp_digits(phone)) >= 10, "your WhatsApp number"),
            (len(pw) >= 8, "a password of at least 8 characters"),
            (pw == pw2, "matching passwords"),
            (gym.strip(), "your gym's name"),
            (members, "how many members you have"),
            (checkins, "how you record visits"),
            (slots is None or pick, "a demo time"),
            (agree and consent, "a tick in both boxes")] if not ok]
        if problems:
            st.error("Please add " + ", ".join(problems) + ".")
            return
        a = {"area": area.strip(), "members": members, "branches": branches, "software": software,
             "checkins": checkins, "worry": worry, "notes": notes.strip()}
        booking, err = (None, None)
        if pick:
            booking, err = book(supabase, cfg, full, email.strip(), phone.strip(), gym.strip(), pick,
                                notes=answers_text(a), members=members)
            if err:
                st.error(err)
                return
        try:
            result = supabase.auth.sign_up({
                "email": email.strip(), "password": pw,
                "options": {"email_redirect_to": "https://usegympulseai.com",
                            "data": {"full_name": full, "business_name": gym.strip(), "account_type": "gym_owner",
                                     "phone": phone.strip(), "referral_code": gag.clean_code(ref) or None,
                                     "demo_first": True, "demo_at": pick.isoformat() if pick else None,
                                     "onboarding": a, "legal": gl.acceptance(email.strip())}}})
        except Exception as error:
            reason = str(error).lower()
            st.error("Too many tries. Please wait a few minutes." if "rate" in reason else
                     "This email is already registered. Sign in on the main page instead." if "already" in reason
                     else "We couldn't create your account. Please check your details and try again.")
            return
        if result.user and not (result.user.identities or []):
            st.error("This email is already registered. Sign in on the main page instead.")
            return
        when = (f"{pick:%A %-d %B} at {pick:%-I:%M %p}") if pick else ""
        if result.session and result.user:              # no email confirmation needed: straight in
            st.session_state.auth_user = {"id": str(result.user.id), "email": result.user.email}
            st.session_state.user_profile = {"full_name": full, "business_name": gym.strip()}
            st.query_params.clear()
            st.rerun()
        st.session_state["pending_confirm_email"] = email.strip()
        st.session_state["start_done"] = {"first": full.split()[0], "when": when}
        st.rerun()


def _style():
    gw._md("""<style>
@import url('https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&display=swap');
html body .stApp label, html body .stApp label p, html body .stApp input, html body .stApp textarea,
html body .stApp [data-baseweb="select"] div, html body .stApp button p, html body .stApp [data-testid="stCaptionContainer"],
html body .stApp .st-sub, html body .stApp .st-eyebrow, html body .stApp .st-sec { font-family:'Instrument Sans',sans-serif !important; }
.st-sec.st-first{border-top:0;padding-top:0;margin-top:4px}
.st-eyebrow{color:var(--gp-muted,#8A96AB);font-size:14px;margin:22px 0 6px}
.st-title{font-family:'Instrument Sans',sans-serif;font-weight:500;letter-spacing:-0.035em;font-size:clamp(32px,5vw,46px);
 line-height:1.06;color:var(--gp-text,#F4F6FA)}
.st-when{margin-top:10px;font-size:17px;color:#B7F34A;font-weight:600}
.st-sub{margin:12px 0 8px;color:var(--gp-muted,#AAB4C3);font-size:15px;line-height:1.6;max-width:560px}
.st-sec{margin:22px 0 2px;padding-top:14px;border-top:1px solid var(--gp-line,rgba(255,255,255,.08));
 font-weight:600;font-size:15px;color:var(--gp-text,#E6EAF0)}
html body .stApp [data-testid="stBaseLinkButton-primary"], html body .stApp [data-testid="stBaseLinkButton-primary"] *{
 color:#0B1220 !important;font-weight:700 !important}
</style>""")
