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
/* ---------- 2026 look: app-style tabs, soft glass cards ---------- */
.st-key-mp_tabs [role="tablist"] { gap: 4px !important; background: rgba(255,255,255,.05); padding: 5px !important;
  border-radius: 999px; border: 1px solid rgba(255,255,255,.07); overflow-x: auto; scrollbar-width: none; }
.st-key-mp_tabs [role="tablist"]::after, .st-key-mp_tabs [role="tablist"] > :not([role="tab"]) { display: none !important; }
.st-key-mp_tabs [role="tab"] { border-radius: 999px !important; padding: 8px 14px !important; white-space: nowrap;
  border: none !important; }
.st-key-mp_tabs [role="tab"] p { font-weight: 700 !important; }
.st-key-mp_tabs [role="tab"][aria-selected="true"] { background: linear-gradient(135deg,#B7F34A,#35D3E8) !important; }
.st-key-mp_tabs [role="tab"][aria-selected="true"] p { color: #0A0F1E !important; }
.st-key-mp_tabs [role="tab"]::after, .st-key-mp_tabs [role="tab"]::before { display: none !important; }
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
    for k in ("mp_step", "mp_email", "mp_choices", "mp_code_tries"):
        st.session_state.pop(k, None)
    st.query_params.clear()
    st.query_params["me"] = str(m["portal_token"])
    st.rerun()


def render_login(supabase):
    render_code_login(supabase, embedded=False)


def render_code_login(supabase, embedded=False):
    """Members sign in: email, then the 6-digit code we email them. No sign-up, no password."""
    if not embedded:
        import gympulse_booking as gb
        gb._header()
    st.markdown(CSS, unsafe_allow_html=True)
    box = st.container(border=True, key="mp_login_card") if embedded else st.container(key="mp_wrap")
    step = st.session_state.get("mp_step", "email")
    with box:
        st.markdown('<div class="auth-title">Member sign in</div>' if embedded else
                    '<div class="bk-title">Your membership</div>', unsafe_allow_html=True)
        sc = _sc()
        if sc is None:
            st.info("Member sign in isn't available yet. Please ask your gym.")
            return
        if step == "email":
            st.caption("Enter the email your gym has for you. We'll email you a 6-digit code: no sign-up and no "
                       "password needed.")
            with st.form("mp_email_form"):
                email = st.text_input("Email", placeholder="you@email.com", key="mp_email_in")
                go = st.form_submit_button("Email me a code", type="primary", use_container_width=True)
            if go:
                e = email.strip().lower()
                n = st.session_state.get("mp_sends", 0)
                if "@" not in e or "." not in e.split("@")[-1]:
                    st.error("Please enter your email address.")
                elif n >= 6:
                    st.error("Too many codes asked for. Please wait a little and try again.")
                else:
                    st.session_state["mp_sends"] = n + 1
                    send_code(sc, e)                      # same next step either way: no guessing who's a member
                    st.session_state["mp_email"] = e
                    st.session_state["mp_step"] = "code"
                    st.rerun()
            st.caption("No email with your gym? Ask the front desk to add it, or to send your private link on "
                       "WhatsApp.")
        elif step == "code":
            e = st.session_state.get("mp_email", "")
            st.info(f"If {e} belongs to a gym member, a 6-digit code is on its way. Check your spam folder too.")
            with st.form("mp_code_form"):
                code = st.text_input("6-digit code", max_chars=6, placeholder="123456", key="mp_code_in")
                go = st.form_submit_button("Sign in", type="primary", use_container_width=True)
            if go:
                digits = "".join(ch for ch in code if ch.isdigit())
                tries = st.session_state.get("mp_code_tries", 0)
                if len(digits) != 6:
                    st.error("The code has 6 numbers.")
                elif tries >= 8:
                    st.error("Too many tries. Ask for a new code.")
                else:
                    st.session_state["mp_code_tries"] = tries + 1
                    ok = _one_per_gym(verify_code(sc, e, digits))
                    if len(ok) == 1:
                        _enter(ok[0])
                    elif ok:
                        st.session_state["mp_choices"] = [m["id"] for m in ok]
                        st.session_state["mp_step"] = "pick"
                        st.rerun()
                    else:
                        st.error("That code isn't right or has expired. Check the email, or ask for a new code.")
            a, b = st.columns(2)
            if a.button("Send a new code", use_container_width=True, key="mp_resend"):
                res = send_code(sc, e)
                (st.warning if res == "recent" else st.success)(
                    "Please wait a minute before asking for another code." if res == "recent" else
                    "A new code is on its way if this email belongs to a member.")
            if b.button("Use a different email", use_container_width=True, key="mp_other"):
                st.session_state["mp_step"] = "email"
                st.rerun()
        else:
            st.markdown("You're a member of more than one gym. Which one would you like to open?")
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
    if st.session_state.get("_mp_seen") != m["id"]:          # once per visit, not on every tap
        st.session_state["_mp_seen"] = m["id"]
        try:
            sc.table("members").update({"portal_seen_at": datetime.now(timezone.utc).isoformat()}).eq("id", m["id"]).execute()
        except Exception:
            pass
    with col, gadm.as_gym({"profile": prof, "gym": gym, "email": ""}):
        flash = st.session_state.pop("mp_flash", None)
        if flash:
            st.success(flash)
        tabs = st.tabs(["Home", "Community", "Classes", "Messages", "My details"], key="mp_tabs")
        with tabs[0]:
            _home(sc, m, gym_name, prof)
        with tabs[1]:
            import gympulse_community as gcom
            gcom.render_member(sc, m, gym_name, prof)
        with tabs[2]:
            _classes(sc, m)
        with tabs[3]:
            _messages(sc, m, gym_name)
        with tabs[4]:
            _details(sc, m, gym_name)


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


def _home(sc, m, gym_name, prof):
    import gympulse_grow as gg
    today = gw.today_local()
    act = _activity(sc, m)
    end = pd.to_datetime(m.get("membership_end"), errors="coerce")
    end = None if pd.isna(end) else end.date()
    label, cls, left = status_of(end, today)
    plan, amount = gg.plan_price({**act, **m}) if act else ("Monthly", 0.0)
    plan_txt = gw._text(m.get("plan_name")) or (gw.plan_phrase(plan).capitalize() + " plan" if act else "")
    photo = m.get("photo") if gw.has_photo(m.get("photo")) else None
    pic = (f'<img src="{photo}" style="width:56px;height:56px;border-radius:50%;object-fit:cover;float:right">'
           if photo else "")
    gw._md(f'<div class="mp-card">{pic}<div class="mp-gym">{gw._esc(gym_name)}</div>'
           f'<div class="mp-hi">Hi {gw._esc(_first(m.get("full_name")))} 👋</div>'
           f'<div class="mp-plan">{gw._esc(plan_txt or "Your membership")}<span class="mp-pill {cls}">{label}</span></div>'
           + (f'<div class="mp-plan" style="color:var(--gp-muted,#93A0B4);margin-top:4px">'
              f'{"Ended" if left is not None and left < 0 else "Runs until"} {end:%A %d %B %Y}</div>' if end else "")
           + '</div>')

    pay = dict((prof.get("settings") or {}).get("collect") or {})
    if left is None or left <= 14 or pay.get("paystack_link"):
        with st.container(border=True):
            st.markdown(f"**Renew** · {gw.plan_phrase(plan).capitalize()} plan" + (f" · ₦{amount:,.0f}" if amount else ""))
            ref = gg.reference_for(m["id"], m.get("full_name"))
            if pay.get("paystack_link"):
                st.link_button("Pay securely with Paystack", pay["paystack_link"], type="primary",
                               use_container_width=True)
            if pay.get("bank_account"):
                st.markdown(f"Or transfer to **{gw._esc(pay.get('bank_name', ''))} · {gw._esc(pay['bank_account'])}**"
                            f" · {gw._esc(pay.get('bank_holder', ''))}, reference **{ref}**")
            if not (pay.get("paystack_link") or pay.get("bank_account")):
                st.caption("Renew at the front desk, or message the gym in Messages.")
            else:
                st.caption("Paid by transfer? Send the receipt in Messages and the gym will confirm it.")
            if pay.get("perk"):
                st.caption(f"Renew early and get {pay['perk']}.")

    at, days = _visit_days(sc, m)
    s = visit_stats(days, today)
    gw.kpi_row([("This month", str(s["month"]), "lime", "visits"),
                ("Weeks in a row", str(s["streak"]), "cyan", "with a visit"),
                ("All visits", str(s["total"]), "white", "since you joined"),
                ("Last visit", f"{s['last']:%d %b}" if s["last"] else "–", "grey", "")])

    code = gw.member_code(m["id"])
    uri = gw.qr_data_uri(code)
    with st.container(border=True):
        st.markdown("**Check in**")
        gw._md(f'<div class="mp-qr">{f"<img src={chr(34)}{uri}{chr(34)} alt=QR>" if uri else ""}'
               f'<div class="mp-code">{code}</div></div>')
        st.caption("Show this at the front desk to check in.")

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


def _classes(sc, m):
    now = datetime.now(gw.APP_TZ).replace(tzinfo=None)
    classes = [c for c in gw._fetch_classes(sc, m["gym_id"]) if now <= c["_start"] <= now + timedelta(days=14)]
    if not classes:
        st.info("No classes in the next two weeks yet. Check back soon.")
        return
    ids = [str(c["id"]) for c in classes]
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
    for c in classes:
        cid = str(c["id"])
        with st.container(border=True):
            a, b = st.columns([3, 1.3], vertical_alignment="center")
            a.markdown(f"**{gw._esc(c.get('name') or 'Class')}**  \n{c['_start']:%a %d %b · %I:%M %p}"
                       + (f"  \n{count.get(cid, 0)} booked" if count.get(cid) else ""))
            if not ready:
                continue
            if cid in mine:
                if b.button("Cancel", key=f"mp_cx_{cid}", use_container_width=True):
                    sc.table("class_bookings").delete().eq("gym_id", m["gym_id"]).eq("class_id", cid) \
                        .eq("member_id", m["id"]).execute()
                    st.session_state["mp_flash"] = "Booking cancelled."
                    st.rerun()
            elif b.button("Book", key=f"mp_bk_{cid}", type="primary", use_container_width=True):
                try:
                    sc.table("class_bookings").insert({"gym_id": m["gym_id"], "class_id": cid,
                                                       "member_id": m["id"]}).execute()
                    st.session_state["mp_flash"] = f"You're booked for {c.get('name') or 'the class'}. See you there!"
                except Exception:
                    st.session_state["mp_flash"] = "You're already booked."
                st.rerun()
    if not ready:
        st.caption("Booking opens soon. Until then, just come along.")


def _messages(sc, m, gym_name):
    try:
        rows = (sc.table("messages").select("direction, body, created_at").eq("gym_id", m["gym_id"])
                .eq("member_id", m["id"]).order("created_at", desc=True).limit(30).execute().data or [])
    except Exception:
        rows = []
    if rows:
        for r in reversed(rows):
            mine = r.get("direction") == "in"
            when = pd.to_datetime(r.get("created_at"), errors="coerce", utc=True)
            when = "" if pd.isna(when) else when.tz_convert(gw.APP_TZ).strftime("%d %b, %I:%M %p")
            gw._md(f'<div class="mp-msg {"mp-in" if mine else "mp-out"}">{gw._esc(r.get("body") or "")}'
                   f'<div class="mp-when">{"You" if mine else gw._esc(gym_name)} · {when}</div></div>')
    else:
        st.caption(f"Messages from {gym_name} appear here.")
    with st.form("mp_msg", clear_on_submit=True):
        text = st.text_area(f"Message {gym_name}", placeholder="Ask a question, send a payment receipt reference…",
                            max_chars=1000)
        go = st.form_submit_button("Send", type="primary", use_container_width=True)
    if go and text.strip():
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


# ------------------------------------------------------------------ the gym's side
def render_owner(supabase, gym_id):
    import gympulse_reports as rp
    import gympulse_signup as gsign
    gw.intro("Member app", ":material/smartphone:",
             "Each member gets their own page: renew and pay, check-in QR code, visits, streak and rewards, class "
             "bookings and messages with you. No app to download and no password: they go to usegympulseai.com, tap "
             "Member, and sign in with their email and a code we send them.")
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
                f"classes. Go to {gw.APP_URL.replace('https://', '')}, tap Member, enter your email and the code we "
                f"send you. Or open: {url}", language=None, wrap_lines=True)
    with c2:
        png = gsign._qr_png(url)
        st.image(png, caption="Print this for your front desk", use_container_width=True)
        rp.download_link("Download QR code", png, "gympulse-member-app-qr.png", "image/png", "mp_qr")
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
