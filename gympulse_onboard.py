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


def book(supabase, cfg, name, email, phone, gym, start):
    """Book the demo. Returns (booking dict or None, error message or None)."""
    import gympulse_booking as gb
    import uuid
    try:
        rows = supabase.rpc("book_demo", {
            "p_name": name, "p_email": email, "p_phone": phone, "p_gym": gym, "p_members": "",
            "p_notes": "Signed up for an account (sign-up demo)",
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
         "members": "", "notes": "", "start": start, "cancel_url": f"{gw.APP_URL}/?demo_cancel={token}"}
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
    gw.table([{"Gym": g["name"], "Owner": g["owner"] or "–", "Email": g["email"],
               "WhatsApp": g.get("phone") or g.get("signup_phone") or "–",
               "Demo": f"{when(g):%a %-d %b, %-I:%M %p}" if when(g) else "–"} for g in wait])
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
