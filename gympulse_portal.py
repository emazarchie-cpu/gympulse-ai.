"""GymPulse AI · Member portal: each member's own page.

  usegympulseai.com (choose "Member") or /?member   sign in: email, then a 6-digit code we email them
  usegympulseai.com/?me=<link>   the member's page (no password; the link is the key)

The page shows the member's plan and end date with a Renew button (the gym's own
Paystack link and bank details), their check-in QR code, visits, streak and reward
points, upcoming classes to book, messages with the gym (replies land in the gym's
Follow-ups) and their details and photo. Members can add it to their phone's home
screen like an app. "Get a new link" signs out every older link.

Everything is read on the server with the service key, always limited to the one
member the link belongs to. Database: sql/phase18_member_portal.sql.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

RESEND_GAP = 60                  # seconds between links for the same member
GOALS = ["Weight loss", "Muscle gain", "General fitness", "Strength", "Endurance", "Sports performance"]
SQL_HINT = ("The member app needs a one-time setup: open Supabase, go to SQL Editor, paste in the file "
            "sql/phase18_member_portal.sql and press Run.")

CSS = """
<style>
.mp-card { border: 1px solid var(--gp-line, #253047); border-radius: 20px; padding: 20px 22px; margin: 4px 0 14px;
  background: radial-gradient(600px 180px at 0% 0%, rgba(183,243,74,0.12), transparent 70%), var(--gp-s1, #101827); }
.mp-gym { color: var(--gp-muted, #93A0B4); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; }
.mp-hi { font-size: 26px; font-weight: 800; margin: 2px 0 6px; color: var(--gp-text, #F4F7FB); }
.mp-plan { color: var(--gp-text, #F4F7FB); font-size: 15px; }
.mp-pill { display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 700;
  margin-left: 6px; vertical-align: 2px; }
.mp-ok { background: rgba(183,243,74,.16); color: #B7F34A; } .mp-warn { background: rgba(255,184,77,.16); color: #FFB84D; }
.mp-bad { background: rgba(255,107,107,.16); color: #FF6B6B; } .mp-none { background: rgba(147,160,180,.16); color: #93A0B4; }
.mp-qr { text-align: center; } .mp-qr img { width: 210px; max-width: 70%; background: #fff; padding: 10px; border-radius: 14px; }
.mp-code { font-family: Menlo, Consolas, monospace; font-size: 22px; letter-spacing: 4px; font-weight: 700;
  color: var(--gp-text, #F4F7FB); margin-top: 6px; }
.mp-msg { border-radius: 14px; padding: 10px 14px; margin: 6px 0; max-width: 85%; font-size: 14px; line-height: 1.45;
  white-space: pre-wrap; }
.mp-in { background: rgba(183,243,74,.14); margin-left: auto; } .mp-out { background: var(--gp-s2, #172033); }
.mp-when { font-size: 11px; color: var(--gp-muted, #93A0B4); margin-top: 4px; }
.st-key-mp_wrap { max-width: 620px; margin: 0 auto; width: 100%; }
/* member sign-in links, same look as the owner card's "Sign up" / "Forgot password?" */
html body .stApp.stApp :is(.st-key-mp_to_setup, .st-key-mp_to_forgot, .st-key-mp_back) button { background: transparent !important;
  border: none !important; box-shadow: none !important; min-height: 0 !important; padding: 2px 0 !important;
  width: 100%; justify-content: center !important; }
html body .stApp.stApp.stApp .st-key-mp_to_setup button p { color: #B7F34A !important; font-size: 14px !important;
  font-weight: 800 !important; margin: 0 !important; white-space: pre !important; }
html body .stApp.stApp.stApp .st-key-mp_to_setup button p::before { content: "First time here?  "; color: #93A0B4; font-weight: 500; }
html body .stApp.stApp.stApp :is(.st-key-mp_to_forgot, .st-key-mp_back) button p { color: #93A0B4 !important; font-size: 12px !important;
  font-weight: 600 !important; margin: 0 !important; }
:is(.st-key-mp_to_setup, .st-key-mp_to_forgot, .st-key-mp_back) button:hover p { text-decoration: underline; }
html body .stApp.stApp.stApp :is(.st-key-mp_to_forgot, .st-key-mp_back) button:hover p { color: #B7F34A !important; }
.mp-auth-sub { text-align: center; color: var(--muted, #93A0B4); font-size: 14px; margin: 0 0 6px; }
/* ---------- 2026 look: app-style tabs, soft glass cards ---------- */
.st-key-mp_tabs [role="tab"] { padding: 7px 8px !important; }   /* five tabs fit a phone */
.st-key-mp_wrap [data-testid="stLayoutWrapper"] > div[class*="st-key"] { border-radius: 24px !important; }
.st-key-mp_wrap [data-testid="stVerticalBlock"][class*="emotion"] { }
.mp-card { border: none !important; border-radius: 28px !important;
  background: radial-gradient(140% 120% at 0% 0%, rgba(183,243,74,.20), transparent 55%),
              radial-gradient(120% 120% at 100% 100%, rgba(53,211,232,.16), transparent 55%), rgba(255,255,255,.04) !important; }
.mp-hi { font-size: 30px !important; letter-spacing: -.6px; }
[class*="st-key-mp_gymrow_"] { border: 1px solid var(--gp-line, #253047); border-radius: 18px; padding: 12px 14px;
  margin-bottom: 10px; background: var(--gp-s1, #101827); }
[class*="st-key-mp_gymrow_"] [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 12px !important; }
[class*="st-key-mp_gymrow_"] [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; flex: 1 1 auto !important; }
[class*="st-key-mp_gymrow_"] [data-testid="stColumn"]:first-child, [class*="st-key-mp_gymrow_"] [data-testid="stColumn"]:last-child {
  flex: 0 0 auto !important; }
.mp-gym-logo { width: 46px; height: 46px; border-radius: 12px; object-fit: contain; background: #fff; padding: 4px; }
.mp-gym-name { font-weight: 800; font-size: 16px; color: var(--gp-text, #F4F7FB); margin-bottom: 4px; }
</style>
"""


def login_url():
    return f"{gw.APP_URL}/?member=1"


def portal_url(token):
    return f"{gw.APP_URL}/?me={token}"


def _sc():
    """The server client, with a few seconds' read cache (gympulse_qcache) so taps stay fast."""
    import gympulse_admin as gadm
    import gympulse_qcache as qc
    raw = gadm.service_client()
    return qc.CachedClient(raw) if raw is not None else None


def _token(value):
    try:
        return str(uuid.UUID(str(value)))
    except Exception:
        return None


def _secret(name, default=""):
    import gympulse_followups as gf
    return gf._secret(name, default)


def _first(name):
    return (str(name or "").split() or ["there"])[0]


def _gym(sc, gym_id):
    g = (sc.table("gyms").select("*").eq("id", gym_id).limit(1).execute().data or [{}])[0]
    p = {}
    if g.get("owner_id"):
        p = (sc.table("profiles").select("*").eq("id", g["owner_id"]).limit(1).execute().data or [{}])[0]
    name = gw._text(p.get("business_name")) or gw._text(g.get("business_name"), "your gym")
    return g, p, name


# ------------------------------------------------------------------ sending the private link
def _email(to, subject, html, text):
    import requests
    key, sender = _secret("RESEND_API_KEY"), _secret("EMAIL_FROM")
    if not (key and sender):
        return False
    r = requests.post("https://api.resend.com/emails", timeout=20, headers={"Authorization": f"Bearer {key}"},
                      json={"from": sender, "to": [to], "subject": subject, "html": html, "text": text})
    return r.status_code < 300


def send_link(sc, member, gym_name, force=False):
    """Email and/or WhatsApp the member their private link. Returns the channels used ([] if none)."""
    import gympulse_email as ge
    import gympulse_whatsapp as gwa
    token = member.get("portal_token")
    if not token:
        return []
    if not force and member.get("portal_sent_at"):
        last = pd.to_datetime(member["portal_sent_at"], utc=True, errors="coerce")
        if not pd.isna(last) and (datetime.now(timezone.utc) - last.to_pydatetime()).total_seconds() < RESEND_GAP:
            return ["recent"]
    url, first, used = portal_url(token), _first(member.get("full_name")), []
    email = gw._text(member.get("email")).strip()
    if "@" in email:
        body = (f'<p>Hi {ge.esc(first)},</p><p>Here is your private link to your <b>{ge.esc(gym_name)}</b> membership '
                "page: renew your plan, show your check-in code at the front desk, and see your visits, rewards and "
                "classes.</p>" + ge.button("Open my membership", url)
                + "<p style='color:#6B7686;font-size:13px'>Keep this link to yourself: it opens your page without a "
                  "password. Tip: open it on your phone and choose <b>Add to Home Screen</b>.</p>")
        text = (f"Hi {first},\n\nYour private link to your {gym_name} membership page:\n{url}\n\n"
                "Keep it to yourself: it opens your page without a password.")
        try:
            if _email(email, f"Your {gym_name} membership page", ge.layout("Your membership page", body,
                                                                            f"Your private link from {gym_name}"),
                      text):
                used.append("email")
        except Exception:
            pass
    digits = gwa.to_digits(member.get("phone"))
    if digits and gwa.ready() and not member.get("whatsapp_opt_out"):
        try:
            gwa.send_template(digits, "gp_member_portal", [first, gym_name], url_suffix=token)
            used.append("whatsapp")
        except Exception:
            pass
    if used:
        try:
            sc.table("members").update({"portal_sent_at": datetime.now(timezone.utc).isoformat()}) \
                .eq("id", member["id"]).execute()
        except Exception:
            pass
    return used


# ------------------------------------------------------------------ public: sign in with an email code
CODE_MINUTES = 10
MAX_TRIES = 5


def _hash(code, member_id):
    import hashlib
    return hashlib.sha256(f"{code}:{member_id}:gympulse-portal".encode()).hexdigest()


def _find(sc, contact):
    try:
        return sc.rpc("gp_portal_find", {"p_contact": contact}).execute().data or []
    except Exception:
        return []


def _member(sc, member_id):
    rows = sc.table("members").select("*").eq("id", member_id).limit(1).execute().data or []
    return rows[0] if rows else None


def send_code(sc, email):
    """Email a 6-digit code for every membership with this email. Returns "sent", "recent" or "none"."""
    import secrets
    import gympulse_email as ge
    now = datetime.now(timezone.utc)
    members = [m for m in (_member(sc, f["member_id"]) for f in _find(sc, email)[:5]) if m]
    if not members:
        return "none"
    for m in members:
        last = pd.to_datetime(m.get("portal_sent_at"), utc=True, errors="coerce")
        if not pd.isna(last) and (now - last.to_pydatetime()).total_seconds() < RESEND_GAP \
                and m.get("portal_code_hash"):
            return "recent"
    code = f"{secrets.randbelow(10 ** 6):06d}"
    gyms = []
    for m in members:
        sc.table("members").update({"portal_code_hash": _hash(code, m["id"]),
                                    "portal_code_expires": (now + timedelta(minutes=CODE_MINUTES)).isoformat(),
                                    "portal_code_tries": 0, "portal_sent_at": now.isoformat()}) \
            .eq("id", m["id"]).execute()
        gyms.append(_gym(sc, m["gym_id"])[2])
    first = _first(members[0].get("full_name"))
    where = ", ".join(dict.fromkeys(gyms))
    body = (f"<p>Hi {ge.esc(first)},</p><p>Here is your code to sign in to your <b>{ge.esc(where)}</b> membership "
            "page on GymPulse AI:</p>" + ge.code_box(code)
            + f"<p>It works for {CODE_MINUTES} minutes. If you didn't ask for it, you can ignore this email.</p>")
    text = (f"Hi {first},\n\nYour GymPulse AI sign-in code: {code}\n\nIt works for {CODE_MINUTES} minutes. "
            "If you didn't ask for it, ignore this email.")
    try:
        _email(gw._text(members[0].get("email")).strip(), f"{code} is your sign-in code",
               ge.layout("Your sign-in code", body, f"Your code for {where}"), text)
    except Exception:
        pass
    return "sent"


def verify_code(sc, email, code):
    """The memberships this code opens (it then stops working). Wrong codes count towards the limit."""
    import hmac
    now = datetime.now(timezone.utc)
    ok = []
    for f in _find(sc, email)[:5]:
        m = _member(sc, f["member_id"])
        if not m or not m.get("portal_code_hash") or int(m.get("portal_code_tries") or 0) >= MAX_TRIES:
            continue
        exp = pd.to_datetime(m.get("portal_code_expires"), utc=True, errors="coerce")
        if pd.isna(exp) or exp.to_pydatetime() < now:
            continue
        if hmac.compare_digest(str(m["portal_code_hash"]), _hash(code, m["id"])):
            ok.append(m)
        else:
            sc.table("members").update({"portal_code_tries": int(m.get("portal_code_tries") or 0) + 1}) \
                .eq("id", m["id"]).execute()
    for m in ok:
        sc.table("members").update({"portal_code_hash": None, "portal_code_tries": 0}).eq("id", m["id"]).execute()
    return ok


# ------------------------------------------------------------------ public: sign in with email and password
PW_MIN = 8
PW_MAX_TRIES = 10            # wrong passwords in a row before sign-in locks
PW_LOCK_MINUTES = 15
PW_ITER = 200_000


def _pw_hash(password):
    """PBKDF2-SHA256 with a random salt: the password itself is never stored."""
    import hashlib
    import secrets
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PW_ITER)
    return f"pbkdf2_sha256${PW_ITER}${salt.hex()}${digest.hex()}"


def _pw_ok(password, stored):
    import hashlib
    import hmac
    try:
        _, rounds, salt, digest = str(stored).split("$")
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds)).hex()
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calc, digest)


def _pw_row(sc, member_id):
    rows = (sc.table("member_passwords").select("*").eq("member_id", member_id).limit(1).execute().data or [])
    return rows[0] if rows else None


def has_password(sc, member_id):
    try:
        return _pw_row(sc, member_id) is not None
    except Exception:
        return False


def set_password(sc, m, password):
    """Save the password for this membership and every other membership with the same email,
    so one password opens all of a member's gyms."""
    ids = {str(m["id"]): m["gym_id"]}
    e = gw._text(m.get("email")).strip().lower()
    if e:
        for f in _find(sc, e)[:5]:
            other = _member(sc, f["member_id"])
            if other and gw._text(other.get("email")).strip().lower() == e:
                ids[str(other["id"])] = other["gym_id"]
    now = datetime.now(timezone.utc).isoformat()
    sc.table("member_passwords").upsert(
        [{"member_id": mid, "gym_id": gid, "hash": _pw_hash(password), "tries": 0, "locked_until": None,
          "updated_at": now} for mid, gid in ids.items()], on_conflict="member_id").execute()


def verify_password(sc, email, password):
    """(memberships this password opens, "ok" | "locked" | "wrong"). Wrong tries count per membership."""
    now = datetime.now(timezone.utc)
    ok, locked = [], False
    for f in _find(sc, email)[:5]:
        m = _member(sc, f["member_id"])
        if not m or gw._text(m.get("email")).strip().lower() != email:
            continue
        row = _pw_row(sc, m["id"])
        if not row:
            continue
        until = pd.to_datetime(row.get("locked_until"), utc=True, errors="coerce")
        if not pd.isna(until) and until.to_pydatetime() > now:
            locked = True
            continue
        if _pw_ok(password, row.get("hash")):
            ok.append(m)
            if row.get("tries"):
                sc.table("member_passwords").update({"tries": 0, "locked_until": None}) \
                    .eq("member_id", m["id"]).execute()
        else:
            tries = int(row.get("tries") or 0) + 1
            upd = {"tries": tries}
            if tries >= PW_MAX_TRIES:
                upd = {"tries": 0, "locked_until": (now + timedelta(minutes=PW_LOCK_MINUTES)).isoformat()}
            sc.table("member_passwords").update(upd).eq("member_id", m["id"]).execute()
    return ok, ("ok" if ok else "locked" if locked else "wrong")


def password_problem(new, again):
    if len(new) < PW_MIN:
        return f"Use at least {PW_MIN} characters."
    if new != again:
        return "The two passwords don't match."
    if new.isdigit() or new.lower() in ("password", "12345678", "password1", "qwertyui"):
        return "That password is too easy to guess. Mix letters and numbers."
    return ""


def _end(m):
    e = pd.to_datetime(m.get("membership_end"), errors="coerce")
    return None if pd.isna(e) else e.date()


def _one_per_gym(members):
    """One membership per gym: the one that runs latest (duplicate records with the same email collapse)."""
    best = {}
    for m in members:
        cur = best.get(m["gym_id"])
        if cur is None or (_end(m) or date.min) > (_end(cur) or date.min):
            best[m["gym_id"]] = m
    return list(best.values())


def _enter(m):
    for k in ("mp_step", "mp_email", "mp_choices", "mp_code_tries", "mp_pw_tries", "mp_verified", "mp_mode",
              "mp_first_hint"):
        st.session_state.pop(k, None)
    st.query_params.clear()
    st.query_params["me"] = str(m["portal_token"])
    st.rerun()


def _open(members):
    """Go straight in with one gym, or ask which gym when the email belongs to several."""
    ok = _one_per_gym(members)
    if len(ok) == 1:
        _enter(ok[0])
    elif ok:
        st.session_state["mp_choices"] = [m["id"] for m in ok]
        st.session_state["mp_step"] = "pick"
        st.rerun()


def email_has_password(sc, email):
    """True when this email already has a password. False for first-timers AND for emails that aren't
    members, so the answer never tells anyone who is a member."""
    try:
        for f in _find(sc, email)[:5]:
            m = _member(sc, f["member_id"])
            if m and gw._text(m.get("email")).strip().lower() == email and has_password(sc, m["id"]):
                return True
    except Exception:
        pass
    return False


def _send(sc, e, mode):
    """Email a code and move to the code step. Returns False when too many codes were asked for."""
    n = st.session_state.get("mp_sends", 0)
    if n >= 6:
        st.error("Too many codes asked for. Please wait a little and try again.")
        return False
    st.session_state["mp_sends"] = n + 1
    send_code(sc, e)                              # same next step either way: no guessing who's a member
    st.session_state.update({"mp_email": e, "mp_mode": mode, "mp_step": "code", "mp_code_tries": 0})
    st.rerun()


def render_login(supabase):
    render_code_login(supabase, embedded=False)


def render_code_login(supabase, embedded=False):
    """Members sign in with email and password, on a card that looks like the owner's.
    First time: "Set up your account" emails a 6-digit code, then they create a password and they're in.
    "Forgot password?" works the same way with a new password."""
    if not embedded:
        import gympulse_booking as gb
        gb._header()
    st.markdown(CSS, unsafe_allow_html=True)
    box = st.container(border=True, key="auth_card") if embedded else st.container(key="mp_wrap")
    step = st.session_state.get("mp_step", "login")
    e = st.session_state.get("mp_email", "")
    with box:
        sc = _sc()
        if sc is None:
            st.markdown('<div class="auth-title">Member sign in</div>', unsafe_allow_html=True)
            st.info("Member sign in isn't available yet. Please ask your gym.")
            return

        def back(key="mp_back"):
            if st.button("Back to sign in", key=key):
                st.session_state["mp_step"] = "login"
                st.rerun()

        def go(to):
            st.session_state.pop("mp_first_hint", None)
            st.session_state["mp_email"] = st.session_state.get("mp_login_email", "").strip().lower() or e
            st.session_state["mp_step"] = to

        if step == "login":
            st.markdown('<div class="auth-title">Welcome back, sign in</div>', unsafe_allow_html=True)
            st.button("Set up your account", key="mp_to_setup", on_click=go, args=("setup",))
            with st.form("mp_login_form", border=False):
                email = st.text_input("Email address", value=e, key="mp_login_email")
                pw = st.text_input("Password", type="password", key="mp_pw_in")
                submit = st.form_submit_button("Sign in with email", type="primary", use_container_width=True)
            st.button("Forgot password?", key="mp_to_forgot", on_click=go, args=("forgot",))
            if submit:
                st.session_state.pop("mp_first_hint", None)
                e = email.strip().lower()
                tries = st.session_state.get("mp_pw_tries", 0)
                if "@" not in e or not pw:
                    st.warning("Enter your email and password.")
                elif tries >= 12:
                    st.error("Too many tries. Tap “Forgot password?” to get a code instead.")
                else:
                    st.session_state["mp_pw_tries"] = tries + 1
                    try:
                        ok, state = verify_password(sc, e, pw)
                    except Exception:
                        ok, state = [], "wrong"
                    if ok:
                        _open(ok)
                    elif state == "locked":
                        st.error(f"Too many wrong passwords. Try again in {PW_LOCK_MINUTES} minutes, or tap "
                                 "“Forgot password?”.")
                    elif not email_has_password(sc, e):
                        st.session_state["mp_first_hint"] = e      # first time: no password created yet
                    else:
                        st.error("That password isn't right. Try again, or tap “Forgot password?”.")
            hint = st.session_state.get("mp_first_hint")
            if hint:
                st.info(f"Looks like it's your first time: there's no password for {hint.replace('@', '&#64;')} "
                        "yet. Set up your account first: we'll email you a code, then you create your password.")
                if st.button("Set up my account", key="mp_hint_setup", type="primary", use_container_width=True):
                    st.session_state.pop("mp_first_hint", None)
                    _send(sc, hint, "setup")
            st.markdown('<div class="auth-secure">Secure sign-in. Your password is never stored in plain text.'
                        '</div>', unsafe_allow_html=True)
        elif step in ("setup", "forgot"):
            setup = step == "setup"
            st.markdown(f'<div class="auth-title">{"Set up your account" if setup else "Reset your password"}'
                        '</div>', unsafe_allow_html=True)
            gw._md('<div class="mp-auth-sub">' + ("Enter the email your gym has for you. We'll email you a "
                   "6-digit code, then you create your password." if setup else
                   "Enter your email. We'll send you a 6-digit code to choose a new password.") + '</div>')
            with st.form("mp_email_form", border=False):
                email = st.text_input("Email address", value=e, key="mp_email_in")
                submit = st.form_submit_button("Email me a code", type="primary", use_container_width=True)
            if submit:
                e = email.strip().lower()
                if "@" not in e or "." not in e.split("@")[-1]:
                    st.error("Please enter your email address.")
                else:
                    _send(sc, e, "setup" if setup else "reset")
            back()
            st.markdown('<div class="auth-secure">No email with your gym? Ask the front desk to add it.</div>',
                        unsafe_allow_html=True)
        elif step == "code":
            first = st.session_state.get("mp_mode") == "setup"
            st.markdown(f'<div class="auth-title">{"Set up your account" if first else "Reset your password"}'
                        '</div>', unsafe_allow_html=True)
            gw._md(f'<div class="mp-auth-sub">If <b>{gw._esc(e)}</b> belongs to a gym member, a 6-digit code '
                   'is on its way. Check your spam folder too.</div>')
            with st.form("mp_code_form", border=False):
                code = st.text_input("6-digit code", max_chars=6, placeholder="123456", key="mp_code_in")
                submit = st.form_submit_button("Continue", type="primary", use_container_width=True)
            if submit:
                digits = "".join(ch for ch in code if ch.isdigit())
                tries = st.session_state.get("mp_code_tries", 0)
                if len(digits) != 6:
                    st.error("The code has 6 numbers.")
                elif tries >= 8:
                    st.error("Too many tries. Ask for a new code.")
                else:
                    st.session_state["mp_code_tries"] = tries + 1
                    ok = verify_code(sc, e, digits)
                    if ok:
                        st.session_state.update({"mp_verified": [m["id"] for m in ok], "mp_step": "setpw"})
                        st.rerun()
                    st.error("That code isn't right or has expired. Check the email, or ask for a new code.")
            if st.button("Send a new code", use_container_width=True, key="mp_resend"):
                res = send_code(sc, e)
                (st.warning if res == "recent" else st.success)(
                    "Please wait a minute before asking for another code." if res == "recent" else
                    "A new code is on its way if this email belongs to a member.")
            back()
        elif step == "setpw":
            members = [m for m in (_member(sc, i) for i in st.session_state.get("mp_verified", [])) if m]
            if not members:
                st.session_state["mp_step"] = "login"
                st.rerun()
            reset = st.session_state.get("mp_mode") == "reset"
            st.markdown(f'<div class="auth-title">{"Choose a new password" if reset else "Create your password"}'
                        '</div>', unsafe_allow_html=True)
            gw._md(f'<div class="mp-auth-sub">You\'ll sign in with <b>{gw._esc(e)}</b> and this password from now '
                   f'on. At least {PW_MIN} characters.</div>')
            with st.form("mp_setpw_form", border=False):
                new = st.text_input("New password", type="password", key="mp_new_pw")
                again = st.text_input("Type it again", type="password", key="mp_new_pw2")
                submit = st.form_submit_button("Save and sign in", type="primary", use_container_width=True)
            if submit:
                problem = password_problem(new, again)
                if problem:
                    st.error(problem)
                else:
                    try:
                        for m in members:
                            set_password(sc, m, new)
                    except Exception:
                        pass                               # passwords not switched on yet: still let them in
                    _open(members)
        else:
            st.markdown('<div class="auth-title">Choose your gym</div>', unsafe_allow_html=True)
            gw._md('<div class="mp-auth-sub">You\'re a member of more than one gym. Which one would you like to '
                   'open?</div>')
            for mid in st.session_state.get("mp_choices", []):
                m = _member(sc, mid)
                if not m:
                    continue
                g, prof, name = _gym(sc, m["gym_id"])
                logo = gw._text(dict((prof.get("settings") or {}).get("email_brand") or {}).get("logo_url"))
                pic = (f'<img src="{gw._esc(logo)}" alt="" class="mp-gym-logo">' if logo else
                       gw.avatar_html(name, None, 46))
                active = status_of(_end(m), gw.today_local())
                with st.container(key=f"mp_gymrow_{mid}"):
                    a, b, c = st.columns([1, 5, 1.6], vertical_alignment="center")
                    gw._md(pic, a)
                    gw._md(f'<div class="mp-gym-name">{gw._esc(name)}</div>'
                           f'<span class="mp-pill {active[1]}" style="margin-left:0">{active[0]}</span>', b)
                    if c.button("Open", key=f"mp_pick_{mid}", type="primary", use_container_width=True):
                        _enter(m)


# ------------------------------------------------------------------ the member's page
def _load_member(sc, token):
    t = _token(token)
    if not t or sc is None:
        return None
    try:
        rows = sc.table("members").select("*").eq("portal_token", t).limit(1).execute().data or []
    except Exception:
        return None
    m = rows[0] if rows else None
    if not m or m.get("archived"):
        return None
    return m


def visit_stats(days, today):
    """days: set of dates. This month, total, last visit, weeks in a row with at least one visit."""
    month = sum(1 for d in days if d.year == today.year and d.month == today.month)
    weeks = {d - timedelta(days=d.weekday()) for d in days}
    wk = today - timedelta(days=today.weekday())
    if wk not in weeks:                       # this week not started yet: count up to last week
        wk -= timedelta(days=7)
    streak = 0
    while wk in weeks:
        streak += 1
        wk -= timedelta(days=7)
    return {"month": month, "total": len(days), "last": max(days) if days else None, "streak": streak}


# ------------------------------------------------------------------ locking out long-expired members
LOCK_CHOICES = {0: "Never lock", 30: "1 month after it ends", 60: "2 months after it ends",
                90: "3 months after it ends"}
LOCK_DEFAULT = 60
LET_BACK_DAYS = 14


def lock_cfg(prof):
    """{"days": 0 | 30 | 60 | 90, "allow": {member_id: "YYYY-MM-DD"}} from the owner's settings."""
    c = dict(((prof or {}).get("settings") or {}).get("member_app") or {})
    days = c.get("lock_days", LOCK_DEFAULT)
    return {"days": int(days) if str(days).isdigit() else LOCK_DEFAULT, "allow": dict(c.get("allow") or {})}


def is_locked(m, prof, today):
    """True when the membership ended longer ago than the gym allows and the GM hasn't let them back in.
    Renewing (a later end date) unlocks it by itself."""
    cfg = lock_cfg(prof)
    end = _end(m)
    if not cfg["days"] or end is None or (today - end).days <= cfg["days"]:
        return False
    until = pd.to_datetime(cfg["allow"].get(str(m["id"])), errors="coerce")
    return pd.isna(until) or until.date() < today


def _locked_screen(m, gym_name):
    end = _end(m)
    first = _first(m.get("full_name"))
    gw._md(f'''<div class="mp-card" style="text-align:center;padding:28px 18px">
      <div style="font-size:40px">🔒</div>
      <div class="bk-title" style="margin:8px 0 6px">Your member app is locked</div>
      <p>Hi {gw._esc(first)}, your membership at <b>{gw._esc(gym_name)}</b> ended on
      <b>{end:%d %B %Y}</b> and hasn't been renewed.</p>
      <p>Please contact <b>{gw._esc(gym_name)}</b> (the front desk or the gym manager) to renew. Your access comes back
      as soon as your membership is renewed.</p></div>''')
    if st.button("Log out", key="mp_locked_out", icon=":material/logout:", use_container_width=True):
        st.query_params.clear()
        st.rerun()


def status_of(end, today):
    if end is None:
        return "No plan yet", "mp-none", None
    left = (end - today).days
    if left < 0:
        return f"Ended {end:%d %b}", "mp-bad", left
    if left <= 7:
        return ("Ends today" if left == 0 else f"Ends in {left} day{'s' if left != 1 else ''}"), "mp-warn", left
    return "Active", "mp-ok", left


def render_portal(supabase, token):
    import gympulse_admin as gadm
    import gympulse_booking as gb
    gb._header()
    st.markdown(CSS, unsafe_allow_html=True)
    sc = _sc()
    m = _load_member(sc, token)
    col = st.container(key="mp_wrap")
    if not m:
        with col:
            st.error("This link doesn't work any more. It may have been replaced by a newer one.")
            st.link_button("Get a new link", login_url(), type="primary", use_container_width=True)
        return
    gym, prof, gym_name = _gym(sc, m["gym_id"])
    import gympulse_billing as gbill
    if gbill.gym_locked(m["gym_id"]):                         # the gym's GymPulse AI plan has ended
        with col:
            gbill.render_gym_locked(gym_name)
        return
    if st.session_state.get("_mp_seen") != m["id"]:          # once per visit, not on every tap
        st.session_state["_mp_seen"] = m["id"]
        try:
            sc.table("members").update({"portal_seen_at": datetime.now(timezone.utc).isoformat()}).eq("id", m["id"]).execute()
        except Exception:
            pass
    if is_locked(m, prof, gw.today_local()):
        with col:
            _locked_screen(m, gym_name)
        return
    st.session_state["_mp_prof"] = prof
    with col, gadm.as_gym({"profile": prof, "gym": gym, "email": ""}):
        flash = st.session_state.pop("mp_flash", None)
        if flash:
            st.success(flash)
        tabs = st.tabs(["Home", "Train", "Classes", "Inbox", "Me"], key="mp_tabs")
        with tabs[0]:
            import gympulse_waiver as gwv
            gwv.render_status(sc, m["gym_id"], m["id"], gym_name, for_member=True, compact=True)
            _home(sc, m, gym_name, prof)
            import gympulse_referrals as gref
            gref.render_member_card(sc, m, gym_name, prof)
        with tabs[1]:
            import gympulse_train as gtr
            gtr.render_member(sc, m, gym_name, prof)
        with tabs[2]:
            _classes(sc, m)
        with tabs[3]:
            _messages(sc, m, gym_name)
        with tabs[4]:
            _details(sc, m, gym_name)
            import gympulse_waiver as gwv
            gwv.render_status(sc, m["gym_id"], m["id"], gym_name, for_member=True)


def _activity(sc, m):
    try:
        return (sc.table("member_activity").select("*").eq("member_id", m["id"]).eq("gym_id", m["gym_id"])
                .limit(1).execute().data or [{}])[0]
    except Exception:
        return {}


def _visit_days(sc, m):
    try:
        rows = (sc.table("checkins").select("checked_in_at").eq("gym_id", m["gym_id"]).eq("member_id", m["id"])
                .order("checked_in_at", desc=True).limit(2000).execute().data or [])
    except Exception:
        rows = []
    at = pd.to_datetime(pd.Series([r.get("checked_in_at") for r in rows], dtype=object), errors="coerce", utc=True,
                        format="ISO8601")
    at = at.dropna().dt.tz_convert(gw.APP_TZ)
    return at, {t.date() for t in at}


MP_DEFAULT_ACCENT = "#5EE0A8"          # mint, when the gym hasn't chosen its own brand colour

MP_CSS = """
<style>
:root { --mp-acc: %(acc)s; --mp-ink: #06231a; --mp-s1: #121b19; --mp-s2: #182522; --mp-muted: #8aa79c;
  --mp-warn-bg: #2a1d0b; --mp-warn-line: #5a3d12; --mp-warn: #ffcf7a; }
.mp2-top { margin: 2px 0 12px; display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.mp2-top .d { color: var(--mp-muted); font-size: 13px; }
.mp2-top h2 { margin: 2px 0 0 !important; padding: 0 !important; font-size: 27px !important; line-height: 1.15 !important;
  letter-spacing: -.5px; font-weight: 750 !important; color: #eef5f2 !important; text-wrap: balance; }
.mp2-top img, .mp2-top .av { width: 48px; height: 48px; border-radius: 50%%; object-fit: cover; flex: 0 0 auto; }
.mp2-top .av { background: var(--mp-s2); display: grid; place-items: center; font-weight: 800; color: var(--mp-acc); }
.mp2-busy { background: var(--mp-s1); border-radius: 22px; padding: 16px 16px 12px; margin-bottom: 12px; }
.mp2-busy .l { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
.mp2-busy .l b { font-size: 18px; color: var(--mp-lvl, var(--mp-acc)); } .mp2-busy .l span { color: var(--mp-muted); font-size: 12.5px; }
.mp2-bars { display: flex; gap: 4px; align-items: flex-end; height: 86px; margin-top: 12px; }
.mp2-bars i { flex: 1; display: block; background: #24423a; border-radius: 5px 5px 2px 2px; min-height: 4px; }
.mp2-bars i.now { background: var(--mp-acc); } .mp2-bars i.past { opacity: .45; }
.mp2-hrs { display: flex; justify-content: space-between; color: #5f7d72; font-size: 11px; margin-top: 5px; }
.mp2-ci { border-radius: 22px; padding: 18px; background: var(--mp-acc); color: var(--mp-ink); display: flex;
  justify-content: space-between; align-items: center; gap: 14px; margin-bottom: 12px; }
.mp2-ci b { display: block; font-size: 21px; font-weight: 800; } .mp2-ci span { font-size: 13px; opacity: .78; }
.mp2-ci .code { font-family: Menlo, Consolas, monospace; font-size: 17px; letter-spacing: 3px; font-weight: 800; margin-top: 8px; }
.mp2-ci img { width: 118px; height: 118px; background: #fff; border-radius: 14px; padding: 7px; flex: 0 0 auto; }
.mp2-alert { border-radius: 16px; padding: 12px 14px; background: var(--mp-warn-bg); border: 1px solid var(--mp-warn-line);
  color: var(--mp-warn); font-size: 14px; margin-bottom: 8px; display: flex; justify-content: space-between; gap: 10px; align-items: center; }
.mp2-alert b { color: #ffe2ab; }
.mp2-mini { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin: 4px 0 14px; }
.mp2-mini div { background: var(--mp-s1); border-radius: 16px; padding: 12px; min-width: 0; }
.mp2-mini b { display: block; font-size: 19px; color: #eef5f2; } .mp2-mini span { color: var(--mp-muted); font-size: 11.5px; }
.mp2-cap { font-size: 11.5px; letter-spacing: .1em; text-transform: uppercase; color: #6f8f83; margin: 6px 2px 8px; }
.mp2-wk { display: grid; grid-template-columns: repeat(7, 1fr); gap: 5px; margin-bottom: 14px; }
.mp2-wk div { background: var(--mp-s1); border-radius: 14px; padding: 8px 0 9px; text-align: center; font-size: 11.5px; color: var(--mp-muted); }
.mp2-wk div b { display: block; font-size: 16px; color: #eef5f2; margin: 2px 0 5px; }
.mp2-wk div i { display: block; width: 7px; height: 7px; border-radius: 4px; margin: 0 auto; }
.mp2-wk div.v i { background: var(--mp-acc); }
.mp2-wk div.today { background: var(--mp-acc); color: var(--mp-ink); } .mp2-wk div.today b { color: var(--mp-ink); }
.mp2-wk div.today.v i { background: var(--mp-ink); }
[class*="st-key-mp2_cls_"] { background: var(--mp-s1); border-radius: 16px; padding: 10px 12px; margin-bottom: 8px; }
[class*="st-key-mp2_cls_"] [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 10px !important; align-items: center; }
[class*="st-key-mp2_cls_"] [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; flex: 1 1 auto !important; }
[class*="st-key-mp2_cls_"] [data-testid="stColumn"]:first-child, [class*="st-key-mp2_cls_"] [data-testid="stColumn"]:last-child { flex: 0 0 auto !important; }
.mp2-t { font-family: Menlo, Consolas, monospace; font-weight: 700; color: var(--mp-acc); font-size: 14px; }
.mp2-cn b { display: block; color: #eef5f2; font-size: 14.5px; } .mp2-cn span { color: var(--mp-muted); font-size: 12px; }
/* chat (Inbox) */
.mp2-chathd { display: flex; gap: 10px; align-items: center; padding: 4px 2px 12px; border-bottom: 1px solid #1d2a26; margin-bottom: 10px; }
.mp2-chathd i { width: 40px; height: 40px; border-radius: 50%%; background: var(--mp-acc); color: var(--mp-ink); display: grid;
  place-items: center; font-style: normal; font-weight: 800; }
.mp2-chathd b { display: block; color: #eef5f2; } .mp2-chathd span { color: var(--mp-muted); font-size: 12px; }
.mp2-b { max-width: 82%%; padding: 10px 13px; border-radius: 18px 18px 18px 6px; background: var(--mp-s2); color: #e6efeb;
  font-size: 14.5px; line-height: 1.45; white-space: pre-wrap; margin: 6px 0; }
.mp2-b.me { margin-left: auto; border-radius: 18px 18px 6px 18px; background: var(--mp-acc); color: var(--mp-ink); }
.mp2-b small { display: block; font-size: 11px; opacity: .65; margin-top: 4px; }
.mp2-day { text-align: center; color: #5f7d72; font-size: 11.5px; margin: 12px 0 4px; }
.st-key-mp2_send [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 8px !important; }
.st-key-mp2_send [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; flex: 1 1 auto !important; }
.st-key-mp2_send [data-testid="stColumn"]:last-child { flex: 0 0 auto !important; }
.st-key-mp_qr button p { white-space: nowrap; }
html body .stApp [class*="st-key-mp2_cls_"] button[kind="secondary"] { background: transparent !important;
  border: 1.5px solid var(--mp-acc) !important; color: var(--mp-acc) !important; }
html body .stApp [class*="st-key-mp2_cls_"] button[kind="secondary"] p { color: var(--mp-acc) !important; }
</style>
"""


def _accent(prof):
    """The gym's own brand colour when it has chosen one, else mint."""
    c = gw._text(dict(dict((prof or {}).get("settings") or {}).get("email_brand") or {}).get("color"))
    return c if c.startswith("#") and len(c) in (4, 7) else MP_DEFAULT_ACCENT


def _busy_now(sc, m, prof):
    """(headline level, colour, people in now or None, [(hour, 0–1, state)]) for today, from the gym's own
    check-ins blended with a typical Lagos pattern (gympulse_train)."""
    import gympulse_train as gtr
    cfg = gtr.traffic_cfg(prof)
    data = gtr.traffic(sc, m["gym_id"], cfg["visit"]) or {}
    nowt = datetime.now(gw.APP_TZ)
    dow = (nowt.weekday() + 1) % 7
    slot = nowt.hour * 2 + nowt.minute // 30
    slots, busy, _w, _peak = gtr.busyness(data.get(dow) or {"days": 0, "slots": {}}, dow, cfg)
    hours = {}
    for x in slots:
        hours.setdefault(x // 2, []).append(busy.get(x, 0))
    bars = [(h, max(v), "now" if h == nowt.hour else "past" if h < nowt.hour else "") for h, v in sorted(hours.items())]
    if slot not in busy:
        return "Closed now", "#8aa79c", None, bars
    lvl, colour = gtr._lvl(busy[slot])
    return lvl, colour, gtr.inside_now(sc, m["gym_id"], cfg["visit"]), bars


def _hour(h):
    return f"{h % 12 or 12}{'am' if h < 12 else 'pm'}"


def _home(sc, m, gym_name, prof):
    import gympulse_grow as gg
    st.markdown(MP_CSS % {"acc": _accent(prof)}, unsafe_allow_html=True)
    today = gw.today_local()
    first = gw._esc(_first(m.get("full_name")))
    act = _activity(sc, m)
    end = pd.to_datetime(m.get("membership_end"), errors="coerce")
    end = None if pd.isna(end) else end.date()
    label, cls, left = status_of(end, today)
    plan, amount = gg.plan_price({**act, **m}) if act else ("Monthly", 0.0)
    at, days = _visit_days(sc, m)
    s = visit_stats(days, today)

    # 1 · today: should I go now?
    try:
        lvl, colour, people, bars = _busy_now(sc, m, prof)
    except Exception:
        lvl, colour, people, bars = None, None, None, []
    head = {"Quiet": f"Good time to train, {first}", "Moderate": f"It's moderately busy, {first}",
            "Busy": f"It's busy right now, {first}", "Closed now": f"The gym is closed now, {first}"}.get(
        lvl, f"Hi {first}")
    photo = m.get("photo") if gw.has_photo(m.get("photo")) else None
    av = (f'<img src="{photo}" alt="">' if photo else f'<div class="av">{first[:1]}</div>')
    gw._md(f'<div class="mp2-top"><div><div class="d">{datetime.now(gw.APP_TZ):%A, %d %B} · {gw._esc(gym_name)}</div>'
           f'<h2>{head}</h2></div>{av}</div>')
    if bars:
        top = max(v for _h, v, _s in bars) or 1
        bar_html = "".join(f'<i class="{st_}" style="height:{max(6, int(v / top * 100))}%" title="{_hour(h)}"></i>'
                           for h, v, st_ in bars)
        ticks = [bars[0][0], bars[len(bars) // 3][0], bars[2 * len(bars) // 3][0], bars[-1][0]]
        sub = (f"about {people} {'person' if people == 1 else 'people'} in" if people else
               "how busy it usually is today")
        gw._md(f'<div class="mp2-busy" style="--mp-lvl:{colour}"><div class="l"><b>{gw._esc(lvl)}</b>'
               f'<span>{sub}</span></div><div class="mp2-bars">{bar_html}</div>'
               f'<div class="mp2-hrs">{"".join(f"<span>{_hour(t)}</span>" for t in ticks)}</div></div>')

    # 2 · check in
    code = gw.member_code(m["id"])
    uri = gw.qr_data_uri(code)
    gw._md(f'<div class="mp2-ci"><div><b>Check in</b><span>Show this at the front desk</span>'
           f'<div class="code">{code}</div></div>' + (f'<img src="{uri}" alt="Check-in code">' if uri else "") + '</div>')

    # 3 · renewal alert (from the week planner)
    pay = dict((prof.get("settings") or {}).get("collect") or {})
    if left is not None and left <= 14:
        when = "ended" if left < 0 else "ends today" if left == 0 else f"ends {end:%a %d %b}"
        gw._md(f'<div class="mp2-alert"><span>Your {gw._esc(gw.plan_phrase(plan))} plan <b>{when}</b></span>'
               + (f'<b>₦{amount:,.0f}</b>' if amount else "") + '</div>')
    if left is None or left <= 14 or pay.get("paystack_link"):
        with st.expander(f"Renew · {gw.plan_phrase(plan).capitalize()} plan" + (f" · ₦{amount:,.0f}" if amount else ""),
                         expanded=left is not None and left <= 7, icon=":material/autorenew:"):
            ref = gg.reference_for(m["id"], m.get("full_name"))
            if pay.get("paystack_link"):
                st.link_button("Pay securely with Paystack", pay["paystack_link"], type="primary",
                               use_container_width=True)
            if pay.get("bank_account"):
                st.markdown(f"Or transfer to **{gw._esc(pay.get('bank_name', ''))} · {gw._esc(pay['bank_account'])}**"
                            f" · {gw._esc(pay.get('bank_holder', ''))}, reference **{ref}**")
            if not (pay.get("paystack_link") or pay.get("bank_account")):
                st.caption("Renew at the front desk, or message the gym in Inbox.")
            else:
                st.caption("Paid by transfer? Send the receipt in Inbox and the gym will confirm it.")
            if pay.get("perk"):
                st.caption(f"Renew early and get {pay['perk']}.")

    # 4 · numbers
    if left is None:
        left_txt, left_sub = "–", "no plan yet"
    elif left < 0:
        left_txt, left_sub = "Ended", f"on {end:%d %b}"
    else:
        left_txt, left_sub = f"{left} day{'s' if left != 1 else ''}", "until renewal"
    gw._md('<div class="mp2-mini">'
           f'<div><b>{left_txt}</b><span>{left_sub}</span></div>'
           f'<div><b>{s["month"]}</b><span>visits this month</span></div>'
           f'<div><b>{s["streak"]} wk</b><span>in a row</span></div></div>')

    # 5 · your week (from the week planner)
    monday = today - timedelta(days=today.weekday())
    week = [monday + timedelta(days=i) for i in range(7)]
    n_week = sum(1 for d in week if d in days)
    gw._md(f'<div class="mp2-cap">Your week · {n_week} visit{"s" if n_week != 1 else ""} so far</div><div class="mp2-wk">'
           + "".join(f'<div class="{" ".join(c for c in ("v" if d in days else "", "today" if d == today else "") if c)}">'
                     f'{d:%a}<b>{d.day}</b><i></i></div>' for d in week) + '</div>')

    # 6 · classes in the next 7 days
    _class_list(sc, m, days_ahead=7, limit=4, title="Classes this week", prefix="h")

    _rewards(sc, m, prof, at)
    st.caption("Tip: on your phone, open the share menu and choose **Add to Home Screen** to keep this page like an "
               "app. Keep the link to yourself.")


def _rewards(sc, m, prof, at):
    import gympulse_loyalty as gl
    cfg = gl.loyalty_cfg(prof)
    if not cfg.get("enabled"):
        return
    try:
        ck = pd.DataFrame({"member_id": m["id"], "at": at.dt.tz_localize(None)})
        if len(ck):
            ck["day"] = ck["at"].dt.normalize()
        else:
            ck = pd.DataFrame(columns=["member_id", "at", "day"])
        try:
            pays = pd.DataFrame(sc.table("payments").select("member_id, kind, paid_on").eq("gym_id", m["gym_id"])
                                .eq("member_id", m["id"]).execute().data or [])
        except Exception:
            pays = None
        reds = [r for r in (gl._redemptions(sc, m["gym_id"]) or []) if r.get("member_id") == m["id"]]
        tbl = gl.points_table(pd.DataFrame([m]), ck, pays, reds, cfg)
        row = tbl.iloc[0] if len(tbl) else None
    except Exception:
        row = None
    if row is None:
        return
    with st.container(border=True):
        st.markdown(f"**Rewards** · {int(row['balance']):,} points")
        if row["ready"] is not None:
            st.success(f"🎁 You can claim **{row['ready']['name']}**. Ask at the front desk.")
        if row["next"] is not None:
            need = int(row["next"]["points"])
            st.progress(min(1.0, max(0.0, float(row["balance"]) / need)) if need else 1.0,
                        text=f"{int(row['to_next']):,} more points to {row['next']['name']}")
        st.caption(f"{int(cfg['per_visit'])} point(s) a visit"
                   + (f", +{int(cfg['week_bonus'])} for {int(cfg['week_visits'])} visits in a week"
                      if int(cfg.get("week_bonus") or 0) else ""))


def _class_list(sc, m, days_ahead=14, limit=None, title=None, prefix="c"):
    """Upcoming classes as rows: time, name and day, and a Book / Booked button."""
    now = datetime.now(gw.APP_TZ).replace(tzinfo=None)
    classes = [c for c in gw._fetch_classes(sc, m["gym_id"]) if now <= c["_start"] <= now + timedelta(days=days_ahead)]
    if title:
        gw._md(f'<div class="mp2-cap">{gw._esc(title)}</div>')
    if not classes:
        st.caption("No classes coming up yet. Check back soon.")
        return
    shown = classes[:limit] if limit else classes
    ids = [str(c["id"]) for c in shown]
    try:
        bk = sc.table("class_bookings").select("class_id, member_id").eq("gym_id", m["gym_id"]) \
            .in_("class_id", ids).execute().data or []
        ready = True
    except Exception:
        bk, ready = [], False
    count = {}
    for b in bk:
        count[b["class_id"]] = count.get(b["class_id"], 0) + 1
    mine = {b["class_id"] for b in bk if b["member_id"] == m["id"]}
    for c in shown:
        cid = str(c["id"])
        with st.container(key=f"mp2_cls_{prefix}_{cid}"):
            a, b, d = st.columns([1, 3, 1.4], vertical_alignment="center")
            a.markdown(f'<span class="mp2-t">{c["_start"]:%H:%M}</span>', unsafe_allow_html=True)
            booked = count.get(cid, 0)
            b.markdown(f'<div class="mp2-cn"><b>{gw._esc(c.get("name") or "Class")}</b>'
                       f'<span>{c["_start"]:%a %d %b}' + (f" · {booked} booked" if booked else "") + '</span></div>',
                       unsafe_allow_html=True)
            if not ready:
                continue
            if cid in mine:
                if d.button("Booked ✓", key=f"mp_cx_{prefix}_{cid}", use_container_width=True,
                            help="Tap to cancel your booking"):
                    sc.table("class_bookings").delete().eq("gym_id", m["gym_id"]).eq("class_id", cid) \
                        .eq("member_id", m["id"]).execute()
                    st.session_state["mp_flash"] = "Booking cancelled."
                    st.rerun()
            elif d.button("Book", key=f"mp_bk_{prefix}_{cid}", type="primary", use_container_width=True):
                try:
                    sc.table("class_bookings").insert({"gym_id": m["gym_id"], "class_id": cid,
                                                       "member_id": m["id"]}).execute()
                    st.session_state["mp_flash"] = f"You're booked for {c.get('name') or 'the class'}. See you there!"
                except Exception:
                    st.session_state["mp_flash"] = "You're already booked."
                st.rerun()
    if limit and len(classes) > limit:
        st.caption(f"{len(classes) - limit} more in the Classes tab.")
    if not ready:
        st.caption("Booking opens soon. Until then, just come along.")


def _classes(sc, m):
    _class_list(sc, m, days_ahead=14, prefix="c")


QUICK_REPLIES = {"Renew": "Hi, I'd like to renew my plan.",
                 "Book a class": "Hi, can you book me into a class this week?",
                 "Freeze": "Hi, I'd like to freeze my membership for a while.",
                 "Question": "Hi, I have a question about my membership."}


def _send_msg(sc, m, gym_name, text):
    row = {"gym_id": m["gym_id"], "member_id": m["id"], "channel": "portal", "direction": "in",
           "body": text.strip(), "status": "received", "is_read": False}
    try:
        sc.table("messages").insert(row).execute()
    except Exception:
        try:
            sc.table("messages").insert({**row, "channel": "email", "subject": "From the member page"}).execute()
        except Exception:
            st.error("Your message couldn't be sent. Please try again later.")
            return
    st.session_state["mp_flash"] = f"Sent. {gym_name} will reply here or on WhatsApp."
    st.rerun()


def _quick_reply(sc, m, gym_name):
    """A quick-reply chip was tapped: send its message, then clear the chip."""
    pick = st.session_state.get("mp_qr")
    st.session_state["mp_qr"] = None
    if not pick:
        return
    try:
        sc.table("messages").insert({"gym_id": m["gym_id"], "member_id": m["id"], "channel": "portal",
                                     "direction": "in", "body": QUICK_REPLIES[pick], "status": "received",
                                     "is_read": False}).execute()
        st.session_state["mp_flash"] = f"Sent. {gym_name} will reply here or on WhatsApp."
    except Exception:
        st.session_state["mp_flash"] = "Your message couldn't be sent. Please try again later."


def _messages(sc, m, gym_name):
    st.markdown(MP_CSS % {"acc": _accent(st.session_state.get("_mp_prof"))}, unsafe_allow_html=True)
    gw._md(f'<div class="mp2-chathd"><i>{gw._esc(gym_name[:1].upper())}</i><div><b>{gw._esc(gym_name)}</b>'
           '<span>Messages with the gym</span></div></div>')
    try:
        rows = (sc.table("messages").select("direction, body, created_at").eq("gym_id", m["gym_id"])
                .eq("member_id", m["id"]).order("created_at", desc=True).limit(40).execute().data or [])
    except Exception:
        rows = []
    if rows:
        last_day = None
        out = []
        for r in reversed(rows):
            mine = r.get("direction") == "in"
            when = pd.to_datetime(r.get("created_at"), errors="coerce", utc=True)
            if not pd.isna(when):
                local = when.tz_convert(gw.APP_TZ)
                day = local.date()
                if day != last_day:
                    out.append(f'<div class="mp2-day">{"Today" if day == gw.today_local() else f"{local:%a %d %b}"}</div>')
                    last_day = day
                t = f"{local:%I:%M %p}".lstrip("0")
            else:
                t = ""
            out.append(f'<div class="mp2-b{" me" if mine else ""}">{gw._esc(r.get("body") or "")}<small>{t}</small></div>')
        gw._md("".join(out))
    else:
        gw._md(f'<div class="mp2-b">Hi {gw._esc(_first(m.get("full_name")))}! Message {gw._esc(gym_name)} here: questions, '
               'payment receipts, bookings or freezing your plan.</div>')
    st.pills("Quick replies", list(QUICK_REPLIES), key="mp_qr", label_visibility="collapsed",
             on_change=_quick_reply, args=(sc, m, gym_name))
    with st.container(key="mp2_send"), st.form("mp_msg", clear_on_submit=True, border=False):
        a, b = st.columns([4, 1.3], vertical_alignment="bottom")
        text = a.text_input(f"Message {gym_name}", placeholder=f"Message {gym_name}…", max_chars=1000,
                            label_visibility="collapsed")
        go = b.form_submit_button("Send", type="primary", use_container_width=True)
    if go and text.strip():
        _send_msg(sc, m, gym_name, text)


def _details(sc, m, gym_name):
    with st.form("mp_details"):
        phone = st.text_input("Phone (WhatsApp)", value=gw._text(m.get("phone")))
        email = st.text_input("Email", value=gw._text(m.get("email")))
        goal_now = gw._text(m.get("fitness_goal"))
        goals = GOALS if goal_now in GOALS or not goal_now else [goal_now] + GOALS
        goal = st.selectbox("Main goal", goals, index=goals.index(goal_now) if goal_now in goals else 2)
        photo = st.file_uploader("New photo (optional)", type=["jpg", "jpeg", "png", "webp", "heic", "heif"])
        save = st.form_submit_button("Save", type="primary", use_container_width=True)
    if save:
        upd = {"phone": phone.strip() or None, "fitness_goal": goal}
        e = email.strip().lower()
        if e and "@" not in e:
            st.error("That email doesn't look right.")
            return
        upd["email"] = e or None
        if photo is not None:
            try:
                upd["photo"] = gw.process_photo(photo.getvalue())
            except Exception:
                st.error("That photo couldn't be read. Try a JPG or PNG.")
                return
        sc.table("members").update(upd).eq("id", m["id"]).eq("gym_id", m["gym_id"]).execute()
        st.session_state["mp_flash"] = "Your details are saved."
        st.rerun()
    st.divider()
    _password_box(sc, m)
    st.divider()
    if st.button("Log out", key="mp_logout", icon=":material/logout:"):
        st.query_params.clear()
        st.rerun()
    st.markdown("**Your private link**")
    st.caption("Lost your phone, or shared the link by mistake? Get a new one: older links stop working.")
    if st.button("Get a new link", key="mp_rotate"):
        new = str(uuid.uuid4())
        sc.table("members").update({"portal_token": new}).eq("id", m["id"]).execute()
        used = send_link(sc, {**m, "portal_token": new}, gym_name, force=True)
        st.session_state["mp_flash"] = ("Done: older links no longer work. This page now uses your new link"
                                        + (", and we've sent it to you by " + " and ".join(used) if used else "")
                                        + ". Save it (Add to Home Screen) so you don't lose it.")
        st.query_params["me"] = new
        st.rerun()


def _password_box(sc, m):
    """Set (first time) or change the password used to sign in with email and password."""
    has = has_password(sc, m["id"])
    st.markdown("**Change your password**" if has else "**Set a password**")
    if not gw._text(m.get("email")).strip():
        st.caption("Add your email above first: you sign in with your email and password.")
        return
    if not has:
        st.caption("Set one so next time you can sign in with your email and password, without waiting for a "
                   "code.")
    with st.form("mp_pw_set"):
        new = st.text_input("New password", type="password", help=f"At least {PW_MIN} characters.")
        again = st.text_input("Type it again", type="password")
        save = st.form_submit_button("Save password", type="primary", use_container_width=True)
    if save:
        problem = password_problem(new, again)
        if problem:
            st.error(problem)
            return
        try:
            set_password(sc, m, new)
        except Exception:
            st.error("Passwords aren't switched on yet. Please ask your gym.")
            return
        st.session_state["mp_flash"] = ("Password saved. Next time, sign in with "
                                        f"{gw._text(m.get('email')).strip()} and this password.")
        st.rerun()


# ------------------------------------------------------------------ the gym's side
def render_owner(supabase, gym_id):
    import gympulse_reports as rp
    import gympulse_signup as gsign
    gw.intro("Member app", ":material/smartphone:",
             "Each member gets their own page: renew and pay, check-in QR code, visits, streak and rewards, class "
             "bookings and messages with you. No app to download: they go to usegympulseai.com, tap Member, and sign in "
             "with their email and password (first time, with a code we email them).")
    try:
        rows = gw.fetch_all(supabase.table("members").select("id, full_name, email, phone, portal_token, "
                                                             "portal_sent_at, portal_seen_at")
                            .eq("gym_id", gym_id).eq("archived", False).order("full_name"))
    except Exception:
        st.info(SQL_HINT)
        return
    seen = sum(1 for r in rows if r.get("portal_seen_at"))
    gw.kpi_row([("Members", f"{len(rows):,}", "cyan", ""), ("Have opened their page", f"{seen:,}", "lime", ""),
                ("Not yet", f"{len(rows) - seen:,}", "amber", "share the link below")])
    url = login_url()
    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown("**Link for your members**")
        st.code(url, language=None)
        st.markdown("**Message for your WhatsApp group**")
        st.code("Your membership is now on your phone 📱 Renew, see your check-in code, visits and rewards, and book "
                f"classes. Go to {gw.APP_URL.replace('https://', '')}, tap Member and sign in with your email (first time, "
                f"we email you a code). Or open: {url}", language=None, wrap_lines=True)
    with c2:
        png = gsign._qr_png(url)
        st.image(png, caption="Print this for your front desk", use_container_width=True)
        rp.download_link("Download QR code", png, "gympulse-member-app-qr.png", "image/png", "mp_qr")
    _owner_lock(supabase, gym_id)
    st.markdown("**Send a member their link**")
    if not rows:
        st.caption("No members yet.")
        return
    by_id = {r["id"]: r for r in rows}
    a, b = st.columns([3, 1], vertical_alignment="bottom")
    pick = a.selectbox("Member", list(by_id), format_func=lambda i: by_id[i]["full_name"], key="mp_pick")
    if b.button("Send link", type="primary", use_container_width=True, key="mp_send"):
        r = by_id[pick]
        if not r.get("portal_token"):
            st.info(SQL_HINT)
            return
        prof = st.session_state.get("user_profile") or {}
        used = send_link(supabase, r, gw._text(prof.get("business_name"), "your gym"), force=True)
        if used:
            st.success(f"Sent to {r['full_name']} by {' and '.join(used)}.")
        else:
            st.warning(f"{r['full_name']} has no email, and WhatsApp isn't set up yet. Send them this link yourself: "
                       f"{portal_url(r['portal_token'])}")


def _owner_lock(supabase, gym_id):
    """Owner: when members whose membership has ended get locked out of the member app, who is locked
    now, and letting someone back in for a short while."""
    import gympulse_grow as gg
    prof = st.session_state.get("user_profile") or {}
    cfg = lock_cfg(prof)
    today = gw.today_local()
    st.markdown("**Lock out members who stop paying**")
    st.caption("When a membership has ended and hasn't been renewed for this long, the member can't open the "
               "member app or sign in any more. They see a message to contact you. Renewing them unlocks it "
               "straight away.")
    owner = st.session_state.get("role") != "staff"
    keys = list(LOCK_CHOICES)
    a, b = st.columns([3, 1], vertical_alignment="bottom")
    pick = a.selectbox("Lock the member app", keys, index=keys.index(cfg["days"]) if cfg["days"] in keys else 2,
                       format_func=LOCK_CHOICES.get, key="mp_lock_days", disabled=not owner)
    if owner and b.button("Save", key="mp_lock_save", use_container_width=True) and pick != cfg["days"]:
        settings = dict(prof.get("settings") or {})
        gg._save_settings(supabase, prof.get("id"),
                          {"member_app": {**dict(settings.get("member_app") or {}), "lock_days": int(pick)}},
                          "Member app lock saved.")
        st.session_state["mm_flash"] = "Member app lock saved: " + LOCK_CHOICES[int(pick)].lower() + "."
        st.rerun()
    try:
        rows = gw.fetch_all(supabase.table("members").select("id, full_name, membership_end")
                            .eq("gym_id", gym_id).eq("archived", False).order("full_name"))
    except Exception:
        rows = []
    locked = [r for r in rows if is_locked(r, prof, today)]
    if not cfg["days"]:
        return
    if not locked:
        st.caption("Nobody is locked out right now.")
        return
    st.caption(f"{len(locked)} member{'s are' if len(locked) != 1 else ' is'} locked out right now.")
    by_id = {r["id"]: r for r in locked}
    c, d = st.columns([3, 1], vertical_alignment="bottom")
    who = c.selectbox("Let a member back in", list(by_id), key="mp_lock_who",
                      format_func=lambda i: f"{by_id[i]['full_name']} · ended {_end(by_id[i]):%d %b %Y}")
    if owner and d.button(f"Let in for {LET_BACK_DAYS} days", key="mp_lock_allow", use_container_width=True):
        settings = dict(prof.get("settings") or {})
        app = dict(settings.get("member_app") or {})
        allow = {k: v for k, v in dict(app.get("allow") or {}).items()
                 if not pd.isna(pd.to_datetime(v, errors="coerce")) and pd.to_datetime(v).date() >= today}
        allow[str(who)] = (today + timedelta(days=LET_BACK_DAYS)).isoformat()
        gg._save_settings(supabase, prof.get("id"), {"member_app": {**app, "allow": allow}}, "Access given back.")
        st.session_state["mm_flash"] = (f"{by_id[who]['full_name']} can use the member app again until "
                                        f"{today + timedelta(days=LET_BACK_DAYS):%d %b}. Renew them to unlock it "
                                        "for good.")
        st.rerun()
