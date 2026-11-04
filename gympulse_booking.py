"""Public "Book a demo" flow for the GymPulse AI website.

?demo=book            booking page: details, date, free time slot
?demo_cancel=<token>  cancel a booking from the link in the confirmation email

Bookings are stored through Supabase functions (sql/demo_bookings.sql), so
visitors never read the table. Every demo uses one Google Meet link
(DEMO_MEET_LINK), and both the client and the owner receive a calendar invite.

Settings (Render environment variables or Streamlit secrets):
  DEMO_MEET_LINK      your permanent Google Meet link, e.g. https://meet.google.com/abc-defg-hij
  DEMO_OWNER_EMAIL    where new bookings are sent (default emmanuel@usegympulseai.com)
  DEMO_EMAIL_FROM     sender of demo emails (default "Emmanuel from GymPulse AI <emmanuel@usegympulseai.com>")
  DEMO_DAYS           working days, default Mon,Tue,Wed,Thu,Fri
  DEMO_HOURS          first and last start time, default 10:00-16:30
  DEMO_SLOT_MINUTES   length of a demo, default 30
  RESEND_API_KEY, EMAIL_FROM   email sending (already used by Follow-ups)
"""
import base64
import os
import uuid
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import quote, urlencode

import streamlit as st

import gympulse_workspaces as gw

TZ = gw.APP_TZ
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MEMBER_RANGES = ["Under 100", "100–300", "300–700", "700–1,500", "Over 1,500"]


def _setting(name, default=""):
    v = os.environ.get(name)
    if v:
        return v.strip()
    try:
        return str(st.secrets.get(name, default) or default).strip()
    except Exception:
        return default


def config():
    days = [d.strip()[:3].title() for d in _setting("DEMO_DAYS", "Mon,Tue,Wed,Thu,Fri").split(",") if d.strip()]
    hours = _setting("DEMO_HOURS", "10:00-16:30").split("-")
    try:
        first = time.fromisoformat(hours[0].strip())
        last = time.fromisoformat(hours[1].strip())
    except Exception:
        first, last = time(10, 0), time(16, 30)
    return {"meet": _setting("DEMO_MEET_LINK"),
            "owner": _setting("DEMO_OWNER_EMAIL", "emmanuel@usegympulseai.com"),
            "sender": _setting("DEMO_EMAIL_FROM", "Emmanuel from GymPulse AI <emmanuel@usegympulseai.com>"),
            "days": [DAY_NAMES.index(d) for d in days if d in DAY_NAMES] or [0, 1, 2, 3, 4],
            "first": first, "last": last,
            "slot": max(15, min(90, int(_setting("DEMO_SLOT_MINUTES", "30") or 30)))}


# ------------------------------------------------------------------ slots
def open_days(cfg, n=21):
    today = datetime.now(TZ).date()
    out, d = [], today
    while len(out) < n:
        if d.weekday() in cfg["days"]:
            out.append(d)
        d += timedelta(days=1)
    return out


def day_slots(cfg, day):
    out, t = [], datetime.combine(day, cfg["first"], tzinfo=TZ)
    end = datetime.combine(day, cfg["last"], tzinfo=TZ)
    while t <= end:
        out.append(t)
        t += timedelta(minutes=cfg["slot"])
    return out


def taken_slots(supabase, day):
    start = datetime.combine(day, time(0, 0), tzinfo=TZ)
    try:
        rows = supabase.rpc("demo_taken_slots", {
            "p_from": start.astimezone(timezone.utc).isoformat(),
            "p_to": (start + timedelta(days=1)).astimezone(timezone.utc).isoformat()}).execute().data or []
    except Exception:
        return None
    taken = set()
    for r in rows:
        v = r if isinstance(r, str) else (list(r.values())[0] if isinstance(r, dict) else r)
        try:
            taken.add(datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(TZ).replace(second=0, microsecond=0))
        except Exception:
            pass
    return taken


def free_slots(supabase, cfg, day):
    taken = taken_slots(supabase, day)
    if taken is None:
        return None
    soon = datetime.now(TZ) + timedelta(hours=2)
    return [s for s in day_slots(cfg, day) if s > soon and s not in taken]


# ------------------------------------------------------------------ calendar
def _ics_time(dt):
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _ics_escape(text):
    return str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def ics_invite(b, cfg):
    start = b["start"]
    end = start + timedelta(minutes=cfg["slot"])
    meet = cfg["meet"] or "Google Meet link to follow by email"
    desc = (f"GymPulse AI demo for {b['gym']}.\nJoin: {meet}\n\n"
            f"Booked by {b['name']} ({b['email']}{', ' + b['phone'] if b['phone'] else ''}).\n"
            f"Members: {b['members'] or 'not given'}.\nNotes: {b['notes'] or 'none'}\n\n"
            f"Need to cancel? {b['cancel_url']}")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//GymPulse AI//Demo booking//EN",
             "CALSCALE:GREGORIAN", "METHOD:REQUEST", "BEGIN:VEVENT",
             f"UID:{b['id']}@usegympulseai.com", f"DTSTAMP:{_ics_time(datetime.now(timezone.utc))}",
             f"DTSTART:{_ics_time(start)}", f"DTEND:{_ics_time(end)}",
             f"SUMMARY:{_ics_escape('GymPulse AI demo · ' + b['gym'])}",
             f"DESCRIPTION:{_ics_escape(desc)}", f"LOCATION:{_ics_escape(meet)}",
             f"ORGANIZER;CN=GymPulse AI:mailto:{cfg['owner']}",
             f"ATTENDEE;CN={_ics_escape(b['name'])};RSVP=TRUE:mailto:{b['email']}",
             "STATUS:CONFIRMED", "BEGIN:VALARM", "TRIGGER:-PT15M", "ACTION:DISPLAY",
             "DESCRIPTION:GymPulse AI demo in 15 minutes", "END:VALARM", "END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"


def google_calendar_url(b, cfg):
    end = b["start"] + timedelta(minutes=cfg["slot"])
    meet = cfg["meet"] or "Google Meet link to follow by email"
    q = {"action": "TEMPLATE", "text": f"GymPulse AI demo · {b['gym']}",
         "dates": f"{_ics_time(b['start'])}/{_ics_time(end)}",
         "details": f"Your 15-minute GymPulse AI demo.\nJoin: {meet}", "location": meet}
    return "https://calendar.google.com/calendar/render?" + urlencode(q, quote_via=quote)


# ------------------------------------------------------------------ email
def _send(to, subject, html, text, ics=None):
    import requests
    # Demo emails come from Emmanuel; EMAIL_FROM stays the sender for gyms' member emails
    key, sender = _setting("RESEND_API_KEY"), config()["sender"] or _setting("EMAIL_FROM")
    if not (key and sender):
        return False
    payload = {"from": sender, "to": [to], "subject": subject, "html": html, "text": text}
    reply = _setting("EMAIL_REPLY_TO") or config()["owner"]
    if reply:
        payload["reply_to"] = reply
    if ics:
        payload["attachments"] = [{"filename": "gympulse-demo.ics",
                                   "content": base64.b64encode(ics.encode()).decode(),
                                   "content_type": "text/calendar; method=REQUEST"}]
    try:
        r = requests.post("https://api.resend.com/emails", json=payload, timeout=20,
                          headers={"Authorization": f"Bearer {key}"})
        return r.status_code < 300
    except Exception:
        return False


def _email_html(title, rows, cta=None, footer=""):
    logo = f"{gw.APP_URL}/app/static/gympulse-email-logo.png"
    body = "".join(f'<tr><td style="padding:6px 0;color:#5B6678;width:140px;vertical-align:top">{gw._esc(k)}</td>'
                   f'<td style="padding:6px 0;color:#111827;font-weight:600">{v}</td></tr>' for k, v in rows)
    button = ""
    if cta:
        button = "".join(
            f'<a href="{gw._esc(url)}" style="display:inline-block;margin:6px 8px 0 0;padding:12px 20px;border-radius:10px;'
            f'background:{"linear-gradient(100deg,#B7F34A,#35D6ED)" if i == 0 else "#F1F4F8"};color:#0A0F1E;'
            f'font-weight:700;text-decoration:none;font-size:14px">{gw._esc(label)}</a>'
            for i, (label, url) in enumerate(cta))
    return f"""<div style="background:#F5F7FA;padding:24px 0;font-family:Arial,Helvetica,sans-serif">
<table role="presentation" width="100%" style="max-width:560px;margin:0 auto;background:#fff;border-radius:16px;overflow:hidden">
<tr><td style="background:#0B1020;padding:20px 24px"><img src="{logo}" alt="GymPulse AI" height="40" style="display:block"></td></tr>
<tr><td style="height:4px;background:linear-gradient(90deg,#B7F34A,#35D6ED)"></td></tr>
<tr><td style="padding:24px">
<h1 style="margin:0 0 12px;font-size:21px;color:#111827">{gw._esc(title)}</h1>
<table role="presentation" style="font-size:14px;border-collapse:collapse">{body}</table>
<div style="margin-top:18px">{button}</div>
<p style="margin:20px 0 0;font-size:12px;color:#5B6678">{footer}</p>
</td></tr></table></div>"""


def send_confirmations(b, cfg):
    when = f"{b['start']:%A %d %B %Y, %I:%M %p} (Lagos time)"
    meet = cfg["meet"]
    ics = ics_invite(b, cfg)
    cal = google_calendar_url(b, cfg)
    join = (f'<a href="{gw._esc(meet)}" style="color:#0B8F5A">{gw._esc(meet)}</a>' if meet
            else "We'll email your Google Meet link before the call.")
    client_html = _email_html(
        f"Your GymPulse AI demo is booked, {b['name'].split(' ')[0]}",
        [("When", gw._esc(when)), ("Length", "15 minutes"), ("Where", "Google Meet"),
         ("Join", join), ("Gym", gw._esc(b["gym"]))],
        [("Join Google Meet", meet)] * bool(meet) + [("Add to Google Calendar", cal)],
        f"Can't make it? <a href=\"{gw._esc(b['cancel_url'])}\" style=\"color:#5B6678\">Cancel this booking</a>. "
        "Reply to this email to pick another time.")
    client_text = (f"Your GymPulse AI demo is booked.\n\nWhen: {when}\nLength: 15 minutes\n"
                   f"Join: {meet or 'Google Meet link to follow by email'}\nAdd to Google Calendar: {cal}\n\n"
                   f"Cancel: {b['cancel_url']}\n")
    owner_html = _email_html(
        f"New demo booked: {b['gym']}",
        [("When", gw._esc(when)), ("Name", gw._esc(b["name"])), ("Email", gw._esc(b["email"])),
         ("WhatsApp", gw._esc(b["phone"] or "—")), ("Gym", gw._esc(b["gym"])),
         ("Members", gw._esc(b["members"] or "—")), ("Notes", gw._esc(b["notes"] or "—"))],
        [("Join Google Meet", meet)] * bool(meet) + [("Add to Google Calendar", cal)]
        + [("WhatsApp them", f"https://wa.me/{gw.whatsapp_digits(b['phone'])}")] * bool(gw.whatsapp_digits(b["phone"])),
        "The calendar invite is attached. Bookings are in Supabase → Table Editor → demo_bookings.")
    owner_text = (f"New demo: {b['gym']}\nWhen: {when}\nName: {b['name']}\nEmail: {b['email']}\n"
                  f"WhatsApp: {b['phone']}\nMembers: {b['members']}\nNotes: {b['notes']}\n")
    sent_client = _send(b["email"], "Your GymPulse AI demo is booked", client_html, client_text, ics)
    _send(cfg["owner"], f"New demo booked · {b['gym']} · {b['start']:%a %d %b %I:%M %p}", owner_html, owner_text, ics)
    return sent_client


# ------------------------------------------------------------------ pages
PAGE_CSS = """
.bk-wrap { max-width: 760px; margin: 0 auto; }
.bk-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: 6px 0 22px; }
.bk-head img { height: 42px; }
.bk-head a { color: #93A1B8 !important; font-size: 13.5px; font-weight: 600; text-decoration: none !important; }
.bk-title { font-family: 'Space Grotesk', 'Inter', sans-serif; font-size: 40px; font-weight: 700;
    letter-spacing: -1.3px; line-height: 1.08; color: #F4F7FB; }
.bk-sub { color: #93A1B8; font-size: 15.5px; line-height: 1.6; margin: 10px 0 18px; }
.bk-points { display: flex; flex-wrap: wrap; gap: 8px 18px; color: #C9D3E3; font-size: 13.5px; margin-bottom: 18px; }
.bk-points span::before { content: "✓ "; color: #B7F34A; font-weight: 800; }
.bk-done { border-radius: 20px; padding: 26px; border: 1px solid rgba(183,243,74,0.35);
    background: radial-gradient(420px 180px at 100% 0%, rgba(53,214,237,0.14), transparent 70%), #10172A; }
.bk-done h2 { margin: 0 0 6px; font-size: 26px; color: #F4F7FB; }
.bk-when { font-size: 18px; font-weight: 700; color: #B7F34A; margin: 10px 0 4px; }
.bk-small { color: #93A1B8; font-size: 13px; line-height: 1.55; }
"""


def _header():
    gw._md(f'<style>{PAGE_CSS}</style><div class="bk-wrap"><div class="bk-head">'
           f'<img src="/app/static/gympulse-email-logo.png" alt="GymPulse AI">'
           f'<a href="./" target="_self">← Back to site</a></div></div>')


def render_router(supabase):
    if st.query_params.get("demo_cancel"):
        return render_cancel(supabase, st.query_params.get("demo_cancel"))
    return render_booking(supabase)


def render_booking(supabase):
    cfg = config()
    _header()
    _, col, _ = st.columns([1, 3.2, 1])
    with col:
        done = st.session_state.get("demo_booked")
        if done:
            return _render_done(done, cfg)
        gw._md('<div class="bk-title">Book a 15-minute demo</div>'
               '<div class="bk-sub">See GymPulse AI with your own gym in mind: who’s drifting, why, '
               'and the plays that keep them. Live on Google Meet with the founder.</div>'
               '<div class="bk-points"><span>No preparation needed</span><span>Google Meet</span>'
               '<span>Free, no obligation</span></div>')
        days = open_days(cfg)
        with st.container(border=True, key="card_demo_form"):
            c1, c2 = st.columns(2)
            name = c1.text_input("Your full name", key="dm_name")
            email = c2.text_input("Email address", key="dm_email",
                                  help="Your confirmation and Google Meet link go here.")
            c3, c4 = st.columns(2)
            gym = c3.text_input("Gym name", key="dm_gym")
            phone = c4.text_input("WhatsApp number (optional)", key="dm_phone",
                                  placeholder="e.g. 0803 000 0000")
            members = st.selectbox("How many members do you have?", MEMBER_RANGES, index=None,
                                   placeholder="Choose a range", key="dm_members")
            day = st.selectbox("Date", days, format_func=lambda d: f"{d:%A %d %B}", key="dm_day")
            slots = free_slots(supabase, cfg, day)
            if slots is None:
                st.warning("Online booking is being set up. Email emmanuel@usegympulseai.com and we'll "
                           "book your demo straight away.")
                return
            if not slots:
                st.info("No free times on that day. Please pick another date.")
                pick = None
            else:
                pick = st.radio("Time (Lagos time, WAT)", slots, horizontal=True, key=f"dm_time_{day}",
                                format_func=lambda s: f"{s:%I:%M %p}".lstrip("0"))
            notes = st.text_area("Anything we should know? (optional)", key="dm_notes", height=80,
                                 placeholder="e.g. we use a spreadsheet today, two locations…")
            go = st.button("Confirm my demo", type="primary", use_container_width=True, key="dm_go",
                           disabled=not pick)
        st.caption("We only use these details to arrange your demo. "
                   "See our Privacy Policy on the main page.")
        if go:
            problem = None
            if not name.strip() or not gym.strip():
                problem = "Please add your name and your gym's name."
            elif "@" not in email or "." not in email.split("@")[-1]:
                problem = "Please enter a valid email address so we can send your confirmation."
            if problem:
                st.error(problem)
                return
            _book(supabase, cfg, name, email, phone, gym, members, notes, pick)


def _book(supabase, cfg, name, email, phone, gym, members, notes, start):
    try:
        rows = supabase.rpc("book_demo", {
            "p_name": name.strip(), "p_email": email.strip(), "p_phone": phone.strip(),
            "p_gym": gym.strip(), "p_members": members or "", "p_notes": notes.strip(),
            "p_starts_at": start.astimezone(timezone.utc).isoformat(),
            "p_duration": cfg["slot"]}).execute().data or []
    except Exception as error:
        msg = str(error)
        if "slot_taken" in msg:
            st.error("Someone just booked that time. Please pick another slot.")
        elif "too_many" in msg:
            st.error("You already have upcoming demos booked. Check your email for the details.")
        elif "bad_time" in msg:
            st.error("That time is no longer available. Please pick another slot.")
        elif "bad_email" in msg:
            st.error("Please check your email address.")
        else:
            st.error("We couldn't book that right now. Please try again, or email emmanuel@usegympulseai.com.")
        return
    row = rows[0] if rows else {}
    token = row.get("cancel_token") or str(uuid.uuid4())
    b = {"id": row.get("booking_id") or token, "name": name.strip(), "email": email.strip().lower(),
         "phone": phone.strip(), "gym": gym.strip(), "members": members or "", "notes": notes.strip(),
         "start": start, "cancel_url": f"{gw.APP_URL}/?demo_cancel={token}"}
    b["emailed"] = send_confirmations(b, cfg)
    st.session_state["demo_booked"] = b
    st.rerun()


def _render_done(b, cfg):
    import gympulse_reports as rp
    meet = cfg["meet"]
    gw._md(f"""<div class="bk-done"><h2>You're booked, {gw._esc(b['name'].split(' ')[0])} 🎉</h2>
        <div class="bk-when">{b['start']:%A %d %B, %I:%M %p} · Lagos time</div>
        <div class="bk-small">15-minute demo on Google Meet for <b>{gw._esc(b['gym'])}</b>.<br>
        {"A confirmation with your Google Meet link and a calendar invite is on its way to <b>" + gw._esc(b['email']) + "</b>."
         if b.get("emailed") else "Save this page or add the demo to your calendar below."}</div></div>""")
    c1, c2 = st.columns(2)
    if meet:
        c1.link_button("Join link: Google Meet", meet, use_container_width=True)
    c2.link_button("Add to Google Calendar", google_calendar_url(b, cfg), use_container_width=True)
    rp.download_link("Download calendar invite (.ics)", ics_invite(b, cfg), "gympulse-demo.ics",
                     "text/calendar", "dm_ics")
    st.caption(f"Need to change it? Reply to the confirmation email, or cancel here: {b['cancel_url']}")
    if st.button("Book another time", type="tertiary", key="dm_again"):
        st.session_state.pop("demo_booked", None)
        st.rerun()


def render_cancel(supabase, token):
    _header()
    _, col, _ = st.columns([1, 3.2, 1])
    with col:
        gw._md('<div class="bk-title">Cancel your demo</div>'
               '<div class="bk-sub">If you cancel, the time is freed for someone else. '
               'You can book again any time.</div>')
        if st.session_state.get("demo_cancelled"):
            st.success("Your demo is cancelled. We hope to see you another time.")
            st.link_button("Book a new time", "./?demo=book", use_container_width=True)
            return
        if st.button("Yes, cancel my demo", type="primary", key="dm_cancel"):
            try:
                rows = supabase.rpc("cancel_demo", {"p_token": str(token)}).execute().data or []
            except Exception:
                rows = None
            if not rows:
                st.error("This link has expired or the demo was already cancelled.")
                return
            r = rows[0]
            cfg = config()
            try:
                when = datetime.fromisoformat(str(r["starts_at"]).replace("Z", "+00:00")).astimezone(TZ)
                when_txt = f"{when:%A %d %B, %I:%M %p}"
            except Exception:
                when_txt = str(r.get("starts_at"))
            _send(cfg["owner"], f"Demo cancelled · {r.get('gym_name')}",
                  _email_html(f"Demo cancelled: {r.get('gym_name')}",
                              [("Was booked for", gw._esc(when_txt)), ("Name", gw._esc(r.get("full_name"))),
                               ("Email", gw._esc(r.get("email")))]),
                  f"Demo cancelled: {r.get('gym_name')} · {when_txt}")
            st.session_state["demo_cancelled"] = True
            st.rerun()
