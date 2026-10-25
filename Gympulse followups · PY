"""GymPulse AI follow-ups: Archie-drafted messages, one-click sending
(WhatsApp + email) and one inbox for every reply."""
import re
import urllib.parse
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

CHANNELS = ["WhatsApp", "Email"]

# Excited, friendly drafts per play: (email subject, message)
DRAFTS = {
    "Personal call": ("We'd love to hear from you, {first}!",
        "Hi {first}! 🎉 It's {owner} from {gym}. We've missed seeing you and I'd love to hear how your {goal} journey is going. Do you have a minute for a quick chat this week? We're cheering for you!"),
    "WhatsApp check-in": ("Checking in, {first}!",
        "Hey {first}! 👋 {owner} from {gym} here. Just wanted to say we're excited about your {goal} goals and we're here to help you smash them. How's training going?"),
    "Free PT session": ("A free session with your trainer, {first}",
        "Hi {first}! 💪 Great news from {gym}: we'd love to treat you to a FREE personal training session to power up your {goal} progress. Want me to book you in this week?"),
    "Renewal offer": ("Keep your momentum going, {first}!",
        "Hi {first}! 🙌 Your {gym} membership is coming up for renewal and we'd hate for you to lose your momentum. Renew this week and we'll make it worth your while. Shall I send the details?"),
    "Class invite": ("Join us for a class, {first}!",
        "Hi {first}! 🔥 We've got an energetic class at {gym} that we think you'll love, and the whole crew would be thrilled to see you there. Can I save you a spot?"),
    "Goal review": ("Let's review your goals, {first}",
        "Hi {first}! 🌟 You've been working towards {goal} and we're so excited to celebrate your progress. Let's grab 15 minutes at {gym} to review your goals and plan your next win!"),
    "Feedback request": ("How are we doing, {first}?",
        "Hi {first}! 😊 Your experience at {gym} matters so much to us. What's one thing we could do to make your training even better? Your feedback genuinely helps us."),
    "Trainer intro": ("Meet your trainer, {first}",
        "Hi {first}! 🤝 We'd love to introduce you to one of our trainers who can help with your {goal} goals. Training with someone who knows you makes all the difference. Can I set up a quick hello?"),
    "Group challenge": ("Join our community challenge, {first}!",
        "Hi {first}! 🏆 We're kicking off a fun group challenge at {gym} and we'd be thrilled to have you on the team. Training together is so much better. Are you in?"),
    "Bring-a-friend invite": ("Bring a friend, {first}!",
        "Hi {first}! 🎊 Bring a friend to {gym} on us this week. Workouts are more fun together, and we can't wait to meet them. Who will you invite?"),
    "Milestone shout-out": ("Congratulations, {first}!",
        "Hi {first}! 🎉 We spotted your progress and we're SO proud of you. Everyone at {gym} is cheering you on towards your {goal} goal. Keep going, you're doing brilliantly!"),
    "Welcome-back note": ("Welcome back, {first}!",
        "Hi {first}! 🌈 It's so good to have you back at {gym}. We've missed your energy and we're excited to help you pick up right where you left off. See you soon!"),
}


def _secret(name, default=""):
    try:
        return str(st.secrets.get(name, default) or default).strip()
    except Exception:
        return default


def email_ready():
    return bool(_secret("RESEND_API_KEY") and _secret("EMAIL_FROM"))


def whatsapp_ready():
    return bool(_secret("WHATSAPP_TOKEN") and _secret("WHATSAPP_PHONE_ID"))


def draft_message(action, name, owner, gym, goal):
    subject, body = DRAFTS.get(action, DRAFTS["Personal call"])
    values = {"first": (str(name).split() or ["there"])[0], "owner": owner,
              "gym": gym, "goal": (goal or "fitness").lower()}
    return subject.format(**values), body.format(**values)


def archie_rewrite(body, name, owner, gym):
    prompt = (f"Rewrite this message to {name} so it sounds genuinely excited, warm "
              f"and personal, like a friendly gym owner. Max 60 words, at most two "
              f"emojis, never mention risk or cancellation, sign off as {owner} from "
              f"{gym}. Reply with ONLY the message.\n\nMessage:\n{body}")
    text, live = gw.archie_reply([{"role": "user", "content": prompt}], "")
    return text.strip(), live


# ---------------------------------------------------------------- sending
def send_email(to, subject, body):
    import requests
    payload = {"from": _secret("EMAIL_FROM"), "to": [to], "subject": subject, "text": body}
    if _secret("EMAIL_REPLY_TO"):
        payload["reply_to"] = _secret("EMAIL_REPLY_TO")
    r = requests.post("https://api.resend.com/emails", json=payload, timeout=20,
                      headers={"Authorization": f"Bearer {_secret('RESEND_API_KEY')}"})
    if r.status_code >= 300:
        raise RuntimeError(f"Email was not sent ({r.status_code}): {r.text[:200]}")
    return r.json().get("id", "")


def send_whatsapp(digits, body, use_template=False):
    import requests
    url = f"https://graph.facebook.com/v20.0/{_secret('WHATSAPP_PHONE_ID')}/messages"
    if use_template:
        payload = {"messaging_product": "whatsapp", "to": digits, "type": "template",
                   "template": {"name": _secret("WHATSAPP_TEMPLATE"),
                                "language": {"code": _secret("WHATSAPP_TEMPLATE_LANG", "en")},
                                "components": [{"type": "body", "parameters": [
                                    {"type": "text", "text": re.sub(r"\s+", " ", body)[:900]}]}]}}
    else:
        payload = {"messaging_product": "whatsapp", "to": digits,
                   "type": "text", "text": {"body": body}}
    r = requests.post(url, json=payload, timeout=20,
                      headers={"Authorization": f"Bearer {_secret('WHATSAPP_TOKEN')}"})
    if r.status_code >= 300:
        hint = ""
        if "131047" in r.text or "re-engage" in r.text.lower():
            hint = (" WhatsApp only allows free-form messages within 24 hours of the "
                    "member's last message. Add an approved template (WHATSAPP_TEMPLATE) "
                    "or use Open in WhatsApp.")
        raise RuntimeError(f"WhatsApp was not sent ({r.status_code}): {r.text[:160]}{hint}")
    return (r.json().get("messages") or [{}])[0].get("id", "")


def log_message(supabase, gym_id, member_id, channel, direction, body,
                subject=None, status="sent", provider_id=None):
    try:
        supabase.table("messages").insert({
            "gym_id": gym_id, "member_id": member_id, "channel": channel,
            "direction": direction, "subject": subject, "body": body,
            "status": status, "provider_id": provider_id or None,
            "is_read": direction == "out"}).execute()
        return True
    except Exception:
        return False


def unread_count(supabase, gym_id):
    """Unread replies, or None when the messages table is not set up yet."""
    try:
        rows = (supabase.table("messages").select("id").eq("gym_id", gym_id)
                .eq("direction", "in").eq("is_read", False).execute().data or [])
        return len(rows)
    except Exception:
        return None


def _in_whatsapp_window(supabase, member_id):
    try:
        rows = (supabase.table("messages").select("created_at").eq("member_id", member_id)
                .eq("direction", "in").eq("channel", "whatsapp")
                .order("created_at", desc=True).limit(1).execute().data or [])
        if not rows:
            return False
        sent = pd.to_datetime(rows[0]["created_at"], utc=True)
        return datetime.now(timezone.utc) - sent.to_pydatetime() < timedelta(hours=24)
    except Exception:
        return False


def _ago(stamp):
    try:
        delta = datetime.now(timezone.utc) - pd.to_datetime(stamp, utc=True).to_pydatetime()
    except Exception:
        return ""
    mins = int(delta.total_seconds() // 60)
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{mins} min ago"
    if mins < 1440:
        return f"{mins // 60} h ago"
    return f"{mins // 1440} d ago"


def _channel_chip(channel):
    return gw.chip("WhatsApp" if channel == "whatsapp" else "Email",
                   "lime" if channel == "whatsapp" else "cyan")


# ---------------------------------------------------------------- callbacks
def _rewrite_cb(key, body, name, owner, gym):
    text, live = archie_rewrite(body, name, owner, gym)
    if live and text:
        st.session_state[key] = text
        st.session_state["fu_note"] = "Archie rewrote your message."
    else:
        st.session_state["fu_note"] = ("Archie's AI is not connected, so the "
                                       "ready-made draft was kept.")


def _reply_cb(member_id, channel):
    st.session_state["fu_member"] = member_id
    st.session_state["fu_channel"] = "WhatsApp" if channel == "whatsapp" else "Email"
    st.session_state["fu_view"] = "Compose"


# ---------------------------------------------------------------- compose
def _compose(supabase, gym_id, members, owner, gym):
    note = st.session_state.pop("fu_note", None)
    if note:
        st.info(note)
    if members.empty:
        st.info("Register members first, then you can message them here.")
        return
    names = dict(zip(members["id"], members["full_name"]))
    ids = list(names)
    if st.session_state.get("fu_member") not in ids:
        st.session_state.pop("fu_member", None)
    mid = st.selectbox("Member", ids, format_func=lambda i: names[i], key="fu_member")
    m = members[members["id"] == mid].iloc[0]
    name, goal = gw._text(m["full_name"]), gw._text(m["fitness_goal"])
    email, phone = gw._text(m["email"]), gw._text(m["phone"])
    digits = gw.whatsapp_digits(phone)

    open_action = ""
    try:
        rows = (supabase.table("retention_actions").select("action_type")
                .eq("member_id", mid).neq("status", "Done").limit(1).execute().data or [])
        open_action = rows[0]["action_type"] if rows else ""
    except Exception:
        pass
    themes = list(DRAFTS)
    theme = st.selectbox("Message idea", themes,
                         index=themes.index(open_action) if open_action in themes else 0,
                         key=f"fu_theme_{mid}",
                         help="Archie drafts an excited message for the idea you pick.")
    options = [c for c in CHANNELS]
    default_channel = "WhatsApp" if digits else "Email"
    if st.session_state.get("fu_channel") not in options:
        st.session_state["fu_channel"] = default_channel
    channel = st.radio("Send via", options, horizontal=True, key="fu_channel")

    gw._md(f'<div class="chip-row">{gw.chip("Drafted by Archie", "lime", dot=True)}'
           f'{gw.chip(theme, "cyan")}</div>')
    subject_default, body_default = draft_message(theme, name, owner, gym, goal)
    base = f"{mid}_{channel}_{theme}"
    body_key = f"fu_body_{base}"
    if channel == "Email":
        subject = st.text_input("Subject", value=subject_default, key=f"fu_subj_{base}")
    else:
        subject = None
    body = st.text_area("Message", value=body_default, height=170, key=body_key)

    c1, c2 = st.columns([1, 1])
    c1.button("Rewrite with Archie", key="fu_rewrite", on_click=_rewrite_cb,
              args=(body_key, body, name, owner, gym), use_container_width=True)

    if channel == "WhatsApp":
        if not digits:
            st.warning(f"{name} has no phone number yet. Add one on their profile.")
            return
        if whatsapp_ready():
            if c2.button("Send on WhatsApp", key="fu_send", use_container_width=True):
                use_t = bool(_secret("WHATSAPP_TEMPLATE")) and not _in_whatsapp_window(supabase, mid)
                try:
                    pid = send_whatsapp(digits, body, use_template=use_t)
                except Exception as error:
                    log_message(supabase, gym_id, mid, "whatsapp", "out", body, status="failed")
                    st.error(str(error))
                else:
                    log_message(supabase, gym_id, mid, "whatsapp", "out", body, provider_id=pid)
                    _after_send(supabase, mid, name)
        else:
            url = f"https://wa.me/{digits}?text={urllib.parse.quote(body)}"
            c2.link_button("Open in WhatsApp", url, use_container_width=True)
            st.caption("Direct sending is not connected yet, so this opens WhatsApp "
                       "with the message ready to send. Tap send there, then mark it below.")
            if st.button("I sent it, log it", key="fu_mark"):
                log_message(supabase, gym_id, mid, "whatsapp", "out", body, status="manual")
                _after_send(supabase, mid, name)
    else:
        if not email:
            st.warning(f"{name} has no email address yet. Add one on their profile.")
            return
        if email_ready():
            if c2.button("Send email", key="fu_send", use_container_width=True):
                try:
                    pid = send_email(email, subject or "", body)
                except Exception as error:
                    log_message(supabase, gym_id, mid, "email", "out", body, subject, status="failed")
                    st.error(str(error))
                else:
                    log_message(supabase, gym_id, mid, "email", "out", body, subject, provider_id=pid)
                    _after_send(supabase, mid, name)
        else:
            url = (f"mailto:{email}?subject={urllib.parse.quote(subject or '')}"
                   f"&body={urllib.parse.quote(body)}")
            c2.link_button("Open in email app", url, use_container_width=True)
            st.caption("Direct sending is not connected yet, so this opens your email "
                       "app with the message ready. Send it there, then mark it below.")
            if st.button("I sent it, log it", key="fu_mark"):
                log_message(supabase, gym_id, mid, "email", "out", body, subject, status="manual")
                _after_send(supabase, mid, name)


def _after_send(supabase, member_id, name):
    """Move the member's To do action to In progress, then confirm."""
    try:
        (supabase.table("retention_actions").update({"status": "In progress"})
         .eq("member_id", member_id).eq("status", "To do").execute())
    except Exception:
        pass
    st.success(f"Message to {name} logged. Their action is now In progress.")


# ----------------------------------------------------------------- inbox
def _inbox(supabase, gym_id, members):
    names = dict(zip(members["id"], members["full_name"]))
    photos = dict(zip(members["id"], members["photo"]))
    a, b, _ = st.columns([1, 1, 3])
    a.button("Refresh", key="fu_refresh", use_container_width=True)
    try:
        rows = (supabase.table("messages").select("*").eq("gym_id", gym_id)
                .eq("direction", "in").order("created_at", desc=True)
                .limit(100).execute().data or [])
    except Exception:
        st.warning("Run follow_up_upgrade.sql in Supabase to turn on the inbox.")
        return
    unread = [r["id"] for r in rows if not r.get("is_read")]
    if unread and b.button("Mark all read", key="fu_markall", use_container_width=True):
        for mid in unread:
            supabase.table("messages").update({"is_read": True}).eq("id", mid).execute()
        st.rerun()
    if not rows:
        st.info("No replies yet. When a member answers on WhatsApp or email, "
                "it will appear here with a notification.")
        return
    for r in rows:
        who = names.get(r["member_id"], "Unknown member")
        with st.container(border=True, key=f"card_in_{r['id']}"):
            c = st.columns([0.6, 5, 1.6], vertical_alignment="center")
            gw._md(gw.avatar_html(who, photos.get(r["member_id"]), 44, "row-tight"), c[0])
            dot = gw.chip("NEW", "lime", dot=True) if not r.get("is_read") else ""
            gw._md(f'<b style="color:#F4F7FB">{gw._esc(who)}</b> {_channel_chip(r["channel"])} {dot}'
                   f'<div class="why" style="padding:2px 0 0">{_ago(r["created_at"])}</div>', c[1])
            c[2].button("Reply", key=f"fu_reply_{r['id']}", on_click=_reply_cb,
                        args=(r["member_id"], r["channel"]), use_container_width=True)
            subj = r.get("subject")
            if subj:
                gw._md(f'<div class="why"><b>Subject:</b> {gw._esc(subj)}</div>')
            gw._md(f'<div class="bubble-in">{gw._esc(r["body"])}</div>')
            if not r.get("is_read") and st.button("Mark as read", key=f"fu_read_{r['id']}"):
                supabase.table("messages").update({"is_read": True}).eq("id", r["id"]).execute()
                st.rerun()


def _sent(supabase, gym_id, members):
    names = dict(zip(members["id"], members["full_name"]))
    try:
        rows = (supabase.table("messages").select("*").eq("gym_id", gym_id)
                .eq("direction", "out").order("created_at", desc=True)
                .limit(50).execute().data or [])
    except Exception:
        st.warning("Run follow_up_upgrade.sql in Supabase to turn on message history.")
        return
    if not rows:
        st.info("Messages you send will be listed here.")
        return
    tone = {"sent": "lime", "manual": "cyan", "failed": "red"}
    for r in rows:
        who = names.get(r["member_id"], "Unknown member")
        with st.container(border=True, key=f"card_out_{r['id']}"):
            gw._md(f'<b style="color:#F4F7FB">{gw._esc(who)}</b> {_channel_chip(r["channel"])} '
                   f'{gw.chip(str(r["status"]).title(), tone.get(r["status"], "grey"), dot=True)}'
                   f'<span class="why"> {_ago(r["created_at"])}</span>')
            gw._md(f'<div class="bubble-out">{gw._esc(r["body"])}</div>')


def render_followups(supabase, gym_id, assess_fn, owner_name, gym_name):
    gw.page_header("Follow-ups",
                   "Send your members an excited message in one click and see every reply, "
                   "from WhatsApp and email, in one place.", "Stay connected")
    flash = st.session_state.pop("fu_flash", None)
    if flash:
        st.success(flash)
    try:
        members, _ = gw.fetch_members(supabase, gym_id, archived=False)
    except Exception as error:
        st.error("Could not load members.")
        with st.expander("Technical details"):
            st.code(str(error))
        return
    unread = unread_count(supabase, gym_id)
    if unread is None:
        st.warning("Messaging needs a one-time database update. Run "
                   "follow_up_upgrade.sql in Supabase, then refresh.")
    chips = [gw.chip("WhatsApp sending " + ("on" if whatsapp_ready() else "ready via link"),
                     "lime" if whatsapp_ready() else "grey", dot=True),
             gw.chip("Email sending " + ("on" if email_ready() else "ready via link"),
                     "lime" if email_ready() else "grey", dot=True)]
    gw._md(f'<div class="chip-row">{"".join(chips)}</div>')

    label = {"Compose": "Compose", "Inbox": f"Inbox ({unread})" if unread else "Inbox",
             "Sent": "Sent"}
    view = st.radio("View", ["Compose", "Inbox", "Sent"], horizontal=True,
                    key="fu_view", format_func=lambda v: label[v],
                    label_visibility="collapsed")
    if view == "Compose":
        _compose(supabase, gym_id, members, owner_name, gym_name)
    elif view == "Inbox":
        _inbox(supabase, gym_id, members)
    else:
        _sent(supabase, gym_id, members)
