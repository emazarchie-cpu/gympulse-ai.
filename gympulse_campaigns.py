"""Branded retention emails that gyms send to their members through GymPulse AI.

* Email branding per gym (logo, gym photo, colour, sender name, company email,
  address, WhatsApp, website), saved in the owner's profile settings.
* A designed email for every retention play: a banner (gym photo + headline +
  tagline + optional offer), a personal message, a button and an unsubscribe link.
* Sending from the gym's own name: straight away "Gym name <gym-name@usegympulseai.com>"
  with replies going to the gym's company inbox, or from the gym's own address once
  their domain is connected (Resend domains API, RESEND_ADMIN_KEY).
* Campaigns: one email to a group of members, personalised, skipping anyone who
  unsubscribed or has no email.

Offers and deadlines only ever come from what the gym types in.
Needs sql/gym_email.sql for unsubscribe links and image hosting; without it,
emails still send with a text banner.
"""
import base64
import io
import os
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import pandas as pd
import streamlit as st

import gympulse_email as ge
import gympulse_workspaces as gw

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = lambda name: os.path.join(HERE, "assets", "fonts", name)
BUCKET = "email-assets"
SEND_DOMAIN = "usegympulseai.com"

# ------------------------------------------------------------------ templates
# {first} {gym} {goal_part} {trainer} {class_name} {class_when} {renew_when} {owner}
TEMPLATES = {
    "Win-back": {
        "subject": "{first}, your spot at {gym} is still here",
        "preheader": "It's never too late to restart.",
        "headline": "COME\nBACK", "kicker": "your spot is still here",
        "body": ["It's been a while since we saw you at {gym}, and we've missed having you around.",
                 "Breaks happen to everyone: work gets busy, plans change, motivation dips. "
                 "What matters is the next step, and it can be a small one.",
                 "<b>Whenever you're ready, we're ready for you.</b> Your coaches are ready to help you{goal_part}, "
                 "and we'll ease you back in at your own pace."],
        "button": "I'm ready to restart", "link": "whatsapp"},
    "WhatsApp check-in": {
        "subject": "We miss you, {first}",
        "preheader": "A quick hello from the {gym} team.",
        "headline": "WE MISS\nYOU", "kicker": "your spot is waiting",
        "body": ["We haven't seen you at {gym} for a little while, and we wanted to say hello.",
                 "Whatever's been going on, we're here to help you get back into your rhythm{goal_part}. "
                 "Even one session this week is a great start."],
        "button": "Book my next session", "link": "whatsapp"},
    "Personal call": {
        "subject": "Can we have a quick chat, {first}?",
        "preheader": "Five minutes to help you get the most from {gym}.",
        "headline": "LET'S\nTALK", "kicker": "five minutes, just for you",
        "body": ["I'd love to hear how your training is going{goal_part} and how we can make {gym} work better for you.",
                 "Reply with a good time to call, or tap the button and we'll find one together."],
        "button": "Pick a time to talk", "link": "whatsapp"},
    "Renewal offer": {
        "subject": "{first}, your membership {renew_when}",
        "preheader": "Keep your progress going at {gym}.",
        "headline": "KEEP\nGOING", "kicker": "your progress is worth it",
        "body": ["Your membership at {gym} {renew_when}.",
                 "You've put in the work{goal_part}, and we'd love to keep helping you. "
                 "Renewing takes a minute, and if anything could be better, just tell us."],
        "button": "Renew my membership", "link": "whatsapp"},
    "Class invite": {
        "subject": "{first}, join us for {class_name}",
        "preheader": "{class_when} at {gym}.",
        "headline": "SEE YOU\nIN CLASS", "kicker": "{class_name}",
        "body": ["We'd love to see you at <b>{class_name}</b>, {class_when}.",
                 "It's a great way to train alongside other members and get back into your rhythm. "
                 "Reply YES and we'll save your spot."],
        "button": "Save my spot", "link": "whatsapp"},
    "Bring-a-friend invite": {
        "subject": "Bring a friend to {gym}, {first}",
        "preheader": "Workouts are better together.",
        "headline": "BETTER\nTOGETHER", "kicker": "bring a friend this week",
        "body": ["Workouts are more fun with a friend, so this week we'd love you to bring one along to {gym}.",
                 "Your friend gets to try {gym}, and you get a training partner who keeps you going."],
        "button": "Invite my friend", "link": "whatsapp"},
    "Trainer intro": {
        "subject": "Meet {trainer}, {first}",
        "preheader": "A coach to help you{goal_part}.",
        "headline": "MEET YOUR\nCOACH", "kicker": "{trainer}",
        "body": ["I'd like you to meet <b>{trainer}</b>, one of our coaches at {gym}.",
                 "{trainer} would love to support you{goal_part}. Training with someone who knows you "
                 "makes all the difference."],
        "button": "Say hello to {trainer}", "link": "whatsapp"},
    "Free PT session": {
        "subject": "A personal training session for you, {first}",
        "preheader": "One-to-one time with a {gym} coach.",
        "headline": "YOUR\nSESSION", "kicker": "one-to-one with a coach",
        "body": ["We'd love to book you a personal training session with {trainer} to fine-tune your plan{goal_part}.",
                 "Tap the button and we'll find a time that suits you."],
        "button": "Book my session", "link": "whatsapp"},
    "Goal review": {
        "subject": "Let's review your goals, {first}",
        "preheader": "15 minutes to plan your next win.",
        "headline": "YOUR NEXT\nWIN", "kicker": "a 15-minute goal review",
        "body": ["You've been working hard{goal_part}, and we'd love to celebrate your progress.",
                 "Let's take 15 minutes at {gym} to review your goals and plan what's next."],
        "button": "Book my goal review", "link": "whatsapp"},
    "Feedback request": {
        "subject": "How are we doing, {first}?",
        "preheader": "One minute to help us improve {gym}.",
        "headline": "YOUR\nVOICE", "kicker": "helps us get better",
        "body": ["Your experience at {gym} matters to us.",
                 "What's one thing we could do to make your training better? Just reply to this email. "
                 "We read every message."],
        "button": "Share my feedback", "link": "reply"},
    "Group challenge": {
        "subject": "Join the challenge, {first}",
        "preheader": "Train together at {gym}.",
        "headline": "TAKE ON\nTHE CHALLENGE", "kicker": "together at {gym}",
        "body": ["We're kicking off a group challenge at {gym} and we'd love you on the team.",
                 "Training together keeps everyone motivated. Reply JOIN and we'll add you."],
        "button": "Count me in", "link": "whatsapp"},
    "Milestone shout-out": {
        "subject": "Congratulations, {first}!",
        "preheader": "Your consistency is paying off.",
        "headline": "WELL\nDONE", "kicker": "your hard work shows",
        "body": ["Everyone at {gym} wanted to say congratulations. Your consistency is really paying off.",
                 "Keep it up. We're proud to be part of your journey{goal_part}."],
        "button": "Keep the streak going", "link": "whatsapp"},
    "Welcome-back note": {
        "subject": "Welcome back, {first}!",
        "preheader": "It's great to see you at {gym} again.",
        "headline": "WELCOME\nBACK", "kicker": "it's good to see you",
        "body": ["It's so good to see you back at {gym}. We missed you.",
                 "We're here to help you pick up right where you left off. Tell us if you need anything."],
        "button": "Plan my next session", "link": "whatsapp"},
}
PLAY_TO_TEMPLATE = {p: p for p in TEMPLATES}
PLAY_TO_TEMPLATE["Renewal check-in"] = "Renewal offer"


# ------------------------------------------------------------------ brand
def brand(profile=None):
    p = profile if isinstance(profile, dict) else (st.session_state.get("user_profile") or {})
    s = dict(p.get("settings") or {})
    b = dict(s.get("email_brand") or {})
    gym = gw._text(p.get("business_name"), "Your gym")
    return {
        "gym": gym,
        "sender_name": gw._text(b.get("sender_name"), gym),
        "company_email": gw._text(b.get("company_email")),
        "color": b.get("color") or "#B7F34A",
        "dark": b.get("dark") or "#0B1020",
        "logo_url": gw._text(b.get("logo_url")),
        "photo_url": gw._text(b.get("photo_url")),
        "address": gw._text(b.get("address")),
        "website": gw._text(b.get("website")),
        "whatsapp": gw._text(b.get("whatsapp") or s.get("biz_phone")),
        "domain": gw._text(b.get("domain")),
        "domain_id": gw._text(b.get("domain_id")),
        "domain_status": gw._text(b.get("domain_status")),
        "sender_email": gw._text(b.get("sender_email")),
        "owner": gw._text(p.get("full_name"), ""),
        "email_theme": "dark" if b.get("email_theme") == "dark" else "light",
    }


def _slug(text):
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return (s or "gym")[:40]


def sender_for(b):
    """(From, Reply-To). Own address once the gym's domain is verified, otherwise the
    gym's name on GymPulse's sending domain, with replies going to the gym."""
    if b["domain_status"] == "verified" and b["sender_email"].lower().endswith("@" + b["domain"].lower()):
        return f'{b["sender_name"]} <{b["sender_email"]}>', b["company_email"] or b["sender_email"]
    return f'{b["sender_name"]} <{_slug(b["gym"])}@{SEND_DOMAIN}>', b["company_email"]


# ------------------------------------------------------------------ assets
def upload_asset(supabase, gym_id, name, data, content_type="image/png"):
    """Store an image in Supabase Storage and return its public URL, or None."""
    path = f"{gym_id}/{name}"
    try:
        store = supabase.storage.from_(BUCKET)
        try:
            store.upload(path, data, {"content-type": content_type, "upsert": "true"})
        except Exception:
            store.update(path, data, {"content-type": content_type, "upsert": "true"})
        url = store.get_public_url(path)
        if isinstance(url, dict):
            url = url.get("publicURL") or url.get("publicUrl") or ""
        return (str(url).split("?")[0] + f"?v={int(time.time())}") if url else None
    except Exception:
        return None


def _fetch_image(url):
    if not url:
        return None
    try:
        import requests
        r = requests.get(url, timeout=10)
        return r.content if r.status_code < 300 else None
    except Exception:
        return None


# ------------------------------------------------------------------ banner
def _hex(c, default=(183, 243, 74)):
    try:
        c = c.lstrip("#")
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return default


def make_banner(headline, kicker="", offer="", color="#B7F34A", dark="#0B1020",
                photo=None, logo=None, gym=""):
    """A 1200x500 banner: gym photo on the left, brand panel with headline on the right."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
    W, H = 1200, 500
    acc, bg = _hex(color), _hex(dark, (11, 16, 32))
    img = Image.new("RGB", (W, H), bg)
    split = 640
    if photo:
        try:
            ph = ImageOps.exif_transpose(Image.open(io.BytesIO(photo))).convert("RGB")
            ph = ImageOps.fit(ph, (split + 80, H), Image.LANCZOS, centering=(0.5, 0.4))
            img.paste(ph, (0, 0))
        except Exception:
            photo = None
    if not photo:
        art = Image.new("RGB", (split + 80, H), tuple(max(0, int(v * 0.55)) for v in bg))
        d = ImageDraw.Draw(art)
        shade = tuple(int(bg[i] * 0.4 + acc[i] * 0.6) for i in range(3))
        for (x, y, r) in [(150, 120, 90), (430, 330, 140), (300, 60, 40), (90, 400, 60), (560, 140, 55)]:
            d.ellipse((x - r, y - r, x + r, y + r), fill=shade)
        d.polygon([(240, 230), (420, 160), (360, 330)], fill=acc)
        img.paste(art.filter(ImageFilter.GaussianBlur(1)), (0, 0))
    # brand panel with a soft diagonal edge
    panel = Image.new("L", (W, H), 0)
    ImageDraw.Draw(panel).polygon([(split, 0), (W, 0), (W, H), (split - 70, H)], fill=255)
    img.paste(Image.new("RGB", (W, H), bg), (0, 0), panel.filter(ImageFilter.GaussianBlur(2)))
    d = ImageDraw.Draw(img)
    x0, right = split + 10, W - 50
    top = 54
    if logo:
        try:
            lg = Image.open(io.BytesIO(logo)).convert("RGBA")
            lg.thumbnail((240, 76), Image.LANCZOS)
            img.paste(lg, (right - lg.width, top - 8), lg)
            top += lg.height + 18
        except Exception:
            logo = None
    if not logo and gym:
        f = ImageFont.truetype(FONT("InterDisplay-Bold.otf"), 34)
        tw = d.textlength(gym, font=f)
        d.text((right - tw, top - 6), gym, font=f, fill=(244, 247, 251))
        d.line([(right - tw, top + 40), (right, top + 40)], fill=acc, width=4)
        top += 66
    lines = [l for l in str(headline).upper().split("\n") if l.strip()][:3] or ["WE MISS YOU"]
    size = 96
    while size > 48:
        f = ImageFont.truetype(FONT("InterDisplay-Black.otf"), size)
        if all(d.textlength(l, font=f) <= right - x0 for l in lines):
            break
        size -= 4
    y = max(top + 10, 150 if len(lines) <= 2 else 120)
    for l in lines:
        tw = d.textlength(l, font=f)
        d.text((right - tw, y), l, font=f, fill=(255, 255, 255))
        y += int(size * 0.98)
    if kicker:
        fk = ImageFont.truetype(FONT("Inter-Medium.otf"), 26)
        k = kicker if d.textlength(kicker, font=fk) <= right - x0 else kicker[:38] + "…"
        d.text((right - d.textlength(k, font=fk), y + 20), k, font=fk, fill=acc)
    if offer:
        fo = ImageFont.truetype(FONT("Inter-SemiBold.otf"), 30)
        o = offer if d.textlength(offer, font=fo) <= right - x0 - 30 else offer[:34] + "…"
        tw = d.textlength(o, font=fo)
        d.text((right - tw, H - 74), o, font=fo, fill=(255, 255, 255))
        cx, cy = right - tw - 24, H - 56
        for ang in range(0, 180, 45):
            import math
            dx, dy = 11 * math.cos(math.radians(ang)), 11 * math.sin(math.radians(ang))
            d.line([(cx - dx, cy - dy), (cx + dx, cy + dy)], fill=acc, width=4)
    d.rectangle([(0, H - 8), (W, H)], fill=acc)
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


# ------------------------------------------------------------------ trainers
TRAINER_TEMPLATES = {"Trainer intro", "Free PT session", "Goal review"}


def trainer_card(t, photo_url=""):
    """What the email shows about a trainer: only what the gym entered."""
    if not t:
        return None
    return {"name": gw._text(t.get("full_name"), "Your coach"),
            "specialty": gw._text(t.get("specialty")),
            "bio": gw._text(t.get("bio")),
            "phone": gw._text(t.get("phone")),
            "photo_url": photo_url,
            "link": gw.trainer_link(t)}


def trainer_photo_bytes(t):
    photo = (t or {}).get("photo")
    if not gw.has_photo(photo):
        return None
    try:
        return base64.b64decode(photo.split(",", 1)[1])
    except Exception:
        return None


def trainer_photo_url(supabase, gym_id, t):
    """Host the trainer's photo so it shows in inboxes ('' if hosting isn't set up)."""
    data = trainer_photo_bytes(t)
    if not data:
        return ""
    return upload_asset(supabase, gym_id, f"trainers/{t['id']}.jpg", data, "image/jpeg") or ""


def with_trainer(ctx, fields):
    card = fields.get("trainer_card")
    return {**ctx, "trainer": card["name"]} if card else ctx


def trainer_picker(prefix, template_name, trainers, default_id=None):
    """Which trainer an email features. Returns the trainer row, or None."""
    if template_name not in TRAINER_TEMPLATES:
        return None
    if not trainers:
        st.info("Add your trainers in Settings → Trainers to show their profile in this email.")
        return None
    ids = [t["id"] for t in trainers]
    by_id = {t["id"]: t for t in trainers}
    idx = ids.index(default_id) if default_id in ids else 0
    c1, c2 = st.columns([2, 1])
    tid = c1.selectbox("Trainer to feature", ids, index=idx, key=f"{prefix}_tr_{template_name}",
                       format_func=lambda i: gw._text(by_id[i].get("full_name"), "Trainer")
                       + (f" · {by_id[i]['specialty']}" if by_id[i].get("specialty") else ""))
    show = c2.toggle("Show their profile", value=True, key=f"{prefix}_trs_{template_name}",
                     help="Adds the trainer's photo, specialty, bio and contact buttons to the email.")
    return by_id[tid], show


def attach_trainer(fields, ctx, t, show):
    """Put the trainer's name and profile card on the email fields (preview photo inline)."""
    if not t:
        return ctx
    data = trainer_photo_bytes(t)
    uri = "data:image/jpeg;base64," + base64.b64encode(data).decode() if data else ""
    fields["trainer_card"] = trainer_card(t, uri)
    fields["show_card"] = show
    fields["_trainer_row"] = t
    return with_trainer(ctx, fields)


def host_trainer_photo(supabase, gym_id, fields):
    """Swap the inline preview photo for a hosted one before sending."""
    card, t = fields.get("trainer_card"), fields.get("_trainer_row")
    if card and t:
        fields["trainer_card"] = {**card, "photo_url": trainer_photo_url(supabase, gym_id, t)}


# The Gmail app on iPhone flips the colours of every email in dark mode, which
# turns a black email light. On black emails, text and coloured blocks sit in
# two blend layers that only Gmail sees (the "u + .body" selector). In dark
# mode they flip those colours back; in light mode they change nothing.
# Backgrounds outside them use background-image, which Gmail does not flip.
GMAIL_DARK_CSS = (
    "u + .body .gp-s{background:#000;mix-blend-mode:screen}"
    "u + .body .gp-d{background:#000;mix-blend-mode:difference}"
    "u + .body .gp-card,u + .body .gp-tbox{background-image:linear-gradient(#000000,#000000)!important}")


def gx(html, P):
    """Keep this block's colours in Gmail's dark mode (black emails only)."""
    if P.get("scheme") != "dark" or not html:
        return html
    return f'<div class="gp-s"><div class="gp-d">{html}</div></div>'


def bgx(color, P):
    """Inline background that Gmail's dark mode leaves alone on black emails."""
    base = f"background-color:{color};"
    return base + (f"background-image:linear-gradient({color},{color});" if P.get("scheme") == "dark" else "")


def trainer_card_email(card, P, acc):
    """A trainer profile block that works in email apps (tables, inline styles)."""
    if not card:
        return ""
    name = ge.esc(card["name"])
    initials = "".join(w[0] for w in card["name"].split()[:2]).upper() or "C"
    if card.get("photo_url"):
        pic = (f'<img src="{ge.esc(card["photo_url"])}" width="84" height="84" alt="{name}" '
               f'style="display:block;width:84px;height:84px;border-radius:42px;border:3px solid {acc};object-fit:cover">')
    else:
        pic = gx(f'<table role="presentation" cellspacing="0" cellpadding="0"><tr><td width="84" height="84" align="center" '
                 f'bgcolor="{acc}" style="width:84px;height:84px;border-radius:42px;background-color:{acc};'
                 f'font-family:Arial,Helvetica,sans-serif;font-size:28px;font-weight:700;color:#0A0F1E">{ge.esc(initials)}</td></tr></table>', P)
    spec = (f'<div style="display:inline-block;margin-top:6px;padding:3px 10px;border-radius:999px;'
            f'background-color:{acc};color:#0A0F1E;font-size:12px;font-weight:700">{ge.esc(card["specialty"])}</div>'
            if card.get("specialty") else "")
    bio = (f'<p style="margin:12px 0 0;font-size:14px;line-height:1.6;color:{P["text"]}">{ge.esc(card["bio"])}</p>'
           if card.get("bio") else "")
    links = []
    digits = gw.whatsapp_digits(card.get("phone"))
    if digits:
        links.append((f"https://wa.me/{digits}", f"WhatsApp {card['name']}"))
    if card.get("phone"):
        links.append((f"tel:{card['phone']}", f"Call {card['phone']}"))
    if card.get("link"):
        links.append((card["link"], "View full profile"))
    link_html = "<br>".join(
        f'<a href="{ge.esc(u)}" style="color:{P["text"]};font-weight:700;text-decoration:underline">{ge.esc(t)}</a>'
        for u, t in links)
    link_html = f'<p style="margin:12px 0 0;font-size:13px;line-height:1.9">{link_html}</p>' if link_html else ""
    text = (f'<div style="font-size:11px;letter-spacing:1px;text-transform:uppercase;color:{P["muted"]}">Your coach</div>'
            f'<div style="font-size:19px;font-weight:700;color:{P["text"]};margin-top:2px">{name}</div>'
            f'{spec}{bio}{link_html}')
    return (f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" bgcolor="{P["box"]}" class="gp-tbox" '
            f'style="margin:4px 0 22px;{bgx(P["box"], P)}border-radius:14px;border:1px solid {P["line"]}"><tr>'
            f'<td width="104" valign="top" style="padding:18px 0 18px 18px">{pic}</td>'
            f'<td valign="top" style="padding:18px 18px 18px 16px;font-family:Arial,Helvetica,sans-serif">'
            f'{gx(text, P)}</td></tr></table>')


# ------------------------------------------------------------------ rendering
def fill(text, ctx):
    try:
        return str(text).format(**ctx)
    except Exception:
        return str(text)


def member_ctx(member, b, extra=None):
    m = dict(member or {})
    first = (gw._text(m.get("name") or m.get("full_name")).split(" ") or ["there"])[0] or "there"
    ctx = {"first": first, "gym": b["gym"], "owner": b["owner"] or b["sender_name"],
           "goal_part": gw._goal_phrase(m.get("goal") or m.get("fitness_goal")),
           "trainer": "one of our coaches", "class_name": "our next class", "class_when": "this week",
           "renew_when": gw._renew_phrase(m.get("renew_days") if "renew_days" in m else m.get("renewal_due_days"))}
    ctx.update({k: v for k, v in (extra or {}).items() if v})
    return ctx


def button_url(kind, b, custom=""):
    if kind == "custom" and custom:
        return custom
    if kind == "website" and b["website"]:
        return b["website"] if b["website"].startswith("http") else "https://" + b["website"]
    if kind == "whatsapp" and gw.whatsapp_digits(b["whatsapp"]):
        return f"https://wa.me/{gw.whatsapp_digits(b['whatsapp'])}"
    if b["company_email"]:
        return f"mailto:{b['company_email']}"
    return ""


def render_email(fields, b, ctx, banner_url, unsub_url=""):
    """The full branded email for one member, on a white or a black background."""
    acc, dark = b["color"], b["dark"]
    theme = fields.get("theme") or b.get("email_theme") or "light"
    ctx = with_trainer(ctx, fields)
    if theme == "dark":
        P = {"page": "#05070D", "card": "#0E1320", "text": "#E8EDF5", "muted": "#9AA6B8",
             "line": "#1F2737", "box": "#161D2C", "scheme": "dark"}
    else:
        P = {"page": "#EEF1F6", "card": "#FFFFFF", "text": "#1F2937", "muted": "#5B6678",
             "line": "#E5E9F0", "box": "#F4F7FB", "scheme": "light"}
    paras = "".join(f'<p style="margin:0 0 16px;font-size:16px;line-height:1.7;color:{P['text']}">{fill(p, ctx)}</p>'
                    for p in fields["body"] if str(p).strip())
    offer = fill(fields.get("offer", ""), ctx)
    offer_html = (f'<div style="margin:6px 0 20px;padding:14px 16px;border-radius:12px;background:{P['box']};'
                  f'border-left:4px solid {acc};font-size:15px;color:{P['text']}"><b>{ge.esc(offer)}</b>'
                  + (f'<br><span style="color:{P['muted']};font-size:13px">{ge.esc(fill(fields.get("terms", ""), ctx))}</span>'
                     if fields.get("terms") else "") + "</div>") if offer else ""
    btn_url = button_url(fields.get("link", "whatsapp"), b, fields.get("custom_link", ""))
    btn = (f'<table role="presentation" cellspacing="0" cellpadding="0" style="margin:4px 0 22px"><tr>'
           f'<td style="border-radius:12px;background:{acc}"><a href="{ge.esc(btn_url)}" '
           f'style="display:inline-block;padding:15px 26px;font-family:Arial,Helvetica,sans-serif;font-size:16px;'
           f'font-weight:700;color:#0A0F1E;text-decoration:none;border-radius:12px">{ge.esc(fill(fields["button"], ctx))}</a>'
           f'</td></tr></table>') if btn_url and fields.get("button") else ""
    sign = ge.esc(fill(fields.get("signoff") or "{owner}\n{gym}", ctx)).replace("\n", "<br>")
    if banner_url:
        hero = (f'<img src="{ge.esc(banner_url)}" width="600" alt="{ge.esc(fill(fields["headline"], ctx).replace(chr(10), " "))}" '
                f'style="display:block;width:100%;max-width:600px;height:auto;border:0">')
    else:
        hl = ge.esc(fill(fields["headline"], ctx)).replace("\n", "<br>")
        hero = gx(f'<div style="background:{dark};padding:34px 28px;text-align:right;font-family:Arial Black,Arial,Helvetica,sans-serif">'
                f'<div style="color:#fff;font-size:15px;font-weight:700;margin-bottom:14px">{ge.esc(b["gym"])}</div>'
                f'<div style="color:#fff;font-size:44px;line-height:1.0;font-weight:900">{hl}</div>'
                f'<div style="color:{acc};font-size:16px;margin-top:10px;font-family:Arial,Helvetica,sans-serif">'
                f'{ge.esc(fill(fields.get("kicker", ""), ctx))}</div></div>', P)
    foot = []
    if b["address"]:
        foot.append(ge.esc(b["address"]))
    contact = " · ".join(x for x in [ge.esc(b["company_email"]), ge.esc(b["whatsapp"]),
                                      ge.esc(b["website"])] if x)
    if contact:
        foot.append(contact)
    if unsub_url:
        foot.append(f'You\'re receiving this because you\'re a member of {ge.esc(b["gym"])}. '
                    f'<a href="{ge.esc(unsub_url)}" style="color:{P['muted']}">Unsubscribe</a>')
    pre = ge.esc(fill(fields.get("preheader", ""), ctx))
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="{P['scheme']} only"><meta name="supported-color-schemes" content="{P['scheme']} only">
<style>:root{{color-scheme:{P['scheme']} only}}{GMAIL_DARK_CSS if P['scheme'] == 'dark' else ''}</style><title>{ge.esc(fill(fields["subject"], ctx))}</title></head>
<body class="body" bgcolor="{P['page']}" style="margin:0;padding:0;{bgx(P['page'], P)}">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{pre}</div>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" bgcolor="{P['page']}" style="{bgx(P['page'], P)}"><tr><td align="center" bgcolor="{P['page']}" style="padding:20px 10px;{bgx(P['page'], P)}">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" bgcolor="{P['card']}" class="gp-card" style="max-width:600px;{bgx(P['card'], P)}border-radius:14px;overflow:hidden;border:1px solid {P['line']}">
<tr><td style="padding:0;line-height:0">{hero}</td></tr>
<tr><td bgcolor="{P['card']}" class="gp-card" style="padding:30px 30px 8px;{bgx(P['card'], P)}font-family:Arial,Helvetica,sans-serif">
{gx(f'<p style="margin:0 0 16px;font-size:16px;line-height:1.7;color:{P["text"]}">Hello {ge.esc(ctx["first"])},</p>' + paras, P)}
{trainer_card_email(fields.get("trainer_card") if fields.get("show_card", True) else None, P, acc)}{gx(offer_html, P)}{gx(btn, P)}
{gx(f'<p style="margin:0 0 22px;font-size:16px;line-height:1.6;color:{P["text"]}">{sign}</p>', P)}
</td></tr>
<tr><td bgcolor="{P['card']}" class="gp-card" style="padding:0 30px 26px;{bgx(P['card'], P)}font-family:Arial,Helvetica,sans-serif">
{gx(f'<div style="padding-top:18px;border-top:1px solid {P["line"]};font-size:12px;line-height:1.6;color:{P["muted"]}">' + '<br>'.join(foot) + '</div>', P)}</td></tr>
</table>
{gx('<div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#8A94A6;padding:12px">Sent with GymPulse AI</div>', P)}
</td></tr></table></body></html>"""


def plain_text(fields, ctx, unsub_url=""):
    ctx = with_trainer(ctx, fields)
    body = "\n\n".join(re.sub("<[^>]+>", "", fill(p, ctx)) for p in fields["body"] if str(p).strip())
    offer = fill(fields.get("offer", ""), ctx)
    card = fields.get("trainer_card") if fields.get("show_card", True) else None
    if card:
        lines = [f"Your coach: {card['name']}" + (f" ({card['specialty']})" if card.get("specialty") else "")]
        lines += [x for x in (card.get("bio"), card.get("phone") and f"Phone: {card['phone']}",
                              card.get("link") and f"Profile: {card['link']}") if x]
        body += "\n\n" + "\n".join(lines)
    return (f"Hello {ctx['first']},\n\n{body}\n\n" + (f"{offer}\n\n" if offer else "")
            + fill(fields.get("signoff") or "{owner}\n{gym}", ctx)
            + (f"\n\nUnsubscribe: {unsub_url}" if unsub_url else ""))


# ------------------------------------------------------------------ simple branded message
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF"
                      "\U00002190-\U000021FF\U00002B00-\U00002BFF\uFE0F\u200D]+")


def no_emoji(text):
    """Emails read as professional letters: emoji stay in WhatsApp only."""
    t = EMOJI_RE.sub("", str(text or ""))
    t = re.sub(r"\*\*?([^*\n]+)\*\*?", r"\1", t)     # WhatsApp *bold* and markdown **bold**
    t = re.sub(r"(?m)^#{1,6}\s*", "", t)
    t = re.sub(r"[ \t]+([,.!?])", r"\1", t)
    return re.sub(r"[ \t]{2,}", " ", t).strip()


def palette(theme):
    if theme == "dark":
        return {"page": "#05070D", "card": "#0E1320", "text": "#E8EDF5", "muted": "#9AA6B8",
                "line": "#1F2737", "box": "#161D2C", "scheme": "dark"}
    return {"page": "#EEF1F6", "card": "#FFFFFF", "text": "#1F2937", "muted": "#5B6678",
            "line": "#E5E9F0", "box": "#F4F7FB", "scheme": "light"}


def logo_is_dark(data):
    """True when a logo is mostly dark ink, so it needs a light header to be seen."""
    if not data:
        return False
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data)).convert("RGBA")
        im.thumbnail((120, 120))
        px = [(r, g, b_) for r, g, b_, a in im.getdata() if a > 60]
        if not px:
            return False
        lum = sum(0.2126 * r + 0.7152 * g + 0.0722 * b_ for r, g, b_ in px) / len(px) / 255
        opaque = len(px) / (im.width * im.height)
        return lum < 0.42 and opaque < 0.97      # dark ink on a transparent background
    except Exception:
        return False


def logo_tone(url):
    """'dark' or 'light' for the gym's logo, cached for the session."""
    if not url:
        return "light"
    cache = st.session_state.setdefault("_logo_tone", {})
    if url not in cache:
        cache[url] = "dark" if logo_is_dark(_fetch_image(url)) else "light"
    return cache[url]


def render_message(b, subject, body, unsub_url="", button=None, preheader="", theme=None):
    """A branded letter from the gym: logo header in the gym's colours, the message,
    an optional button, and the gym's footer. White or black background."""
    P = palette(theme or b.get("email_theme") or "light")
    acc, dark = b["color"], b["dark"]
    text = no_emoji(body)
    paras = "".join(
        f'<p style="margin:0 0 16px;font-size:16px;line-height:1.7;color:{P["text"]}">'
        f'{ge.esc(p.strip()).replace(chr(10), "<br>")}</p>'
        for p in re.split(r"\n\s*\n", text) if p.strip())
    if b.get("logo_url") and logo_tone(b["logo_url"]) == "dark":
        dark = "#FFFFFF"              # dark logo: white header so it stays visible
    if b.get("logo_url"):
        brand_html = (f'<img src="{ge.esc(b["logo_url"])}" alt="{ge.esc(b["gym"])}" height="44" '
                      f'style="display:block;height:44px;max-width:220px;width:auto;border:0">')
    else:
        brand_html = (f'<div style="font-family:Arial Black,Arial,Helvetica,sans-serif;font-size:20px;'
                      f'font-weight:900;color:#FFFFFF;letter-spacing:.5px">{ge.esc(b["gym"])}</div>')
    header = (f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" bgcolor="{dark}" '
              f'style="background-color:{dark};background-image:linear-gradient({dark},{dark})"><tr>'
              f'<td style="padding:22px 28px">{brand_html}</td></tr>'
              f'<tr><td height="4" bgcolor="{acc}" style="height:4px;line-height:4px;font-size:0;'
              f'background-color:{acc};background-image:linear-gradient({acc},{acc})">&nbsp;</td></tr></table>')
    btn = ""
    if button and button[1]:
        btn = (f'<table role="presentation" cellspacing="0" cellpadding="0" style="margin:4px 0 22px"><tr>'
               f'<td bgcolor="{acc}" style="border-radius:12px;background-color:{acc}"><a href="{ge.esc(button[1])}" '
               f'style="display:inline-block;padding:14px 24px;font-family:Arial,Helvetica,sans-serif;font-size:15px;'
               f'font-weight:700;color:#0A0F1E;text-decoration:none;border-radius:12px">{ge.esc(button[0])}</a>'
               f'</td></tr></table>')
    foot = []
    if b.get("address"):
        foot.append(ge.esc(b["address"]))
    contact = " · ".join(x for x in [ge.esc(b.get("company_email")), ge.esc(b.get("whatsapp")),
                                      ge.esc(b.get("website"))] if x)
    if contact:
        foot.append(contact)
    if unsub_url:
        foot.append(f'You\'re receiving this because you\'re a member of {ge.esc(b["gym"])}. '
                    f'<a href="{ge.esc(unsub_url)}" style="color:{P["muted"]}">Unsubscribe</a>')
    foot_html = gx(f'<div style="padding-top:18px;border-top:1px solid {P["line"]};font-size:12px;line-height:1.6;'
                   f'color:{P["muted"]}">' + "<br>".join(foot) + "</div>", P) if foot else ""
    pre = ge.esc(no_emoji(preheader or text.split("\n")[0])[:140])
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="{P['scheme']} only"><meta name="supported-color-schemes" content="{P['scheme']} only">
<style>:root{{color-scheme:{P['scheme']} only}}{GMAIL_DARK_CSS if P['scheme'] == 'dark' else ''}</style><title>{ge.esc(no_emoji(subject))}</title></head>
<body class="body" bgcolor="{P['page']}" style="margin:0;padding:0;{bgx(P['page'], P)}">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{pre}</div>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" bgcolor="{P['page']}" style="{bgx(P['page'], P)}"><tr><td align="center" bgcolor="{P['page']}" style="padding:20px 10px;{bgx(P['page'], P)}">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" bgcolor="{P['card']}" class="gp-card" style="max-width:600px;{bgx(P['card'], P)}border-radius:14px;overflow:hidden;border:1px solid {P['line']}">
<tr><td style="padding:0">{header}</td></tr>
<tr><td bgcolor="{P['card']}" class="gp-card" style="padding:30px 30px 8px;{bgx(P['card'], P)}font-family:Arial,Helvetica,sans-serif">
{gx(paras, P)}{gx(btn, P)}
</td></tr>
<tr><td bgcolor="{P['card']}" class="gp-card" style="padding:0 30px 26px;{bgx(P['card'], P)}font-family:Arial,Helvetica,sans-serif">{foot_html}</td></tr>
</table>
{gx('<div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#8A94A6;padding:12px">Sent with GymPulse AI</div>', P)}
</td></tr></table></body></html>"""


def email_member(supabase, gym_id, member, subject, body, button=None):
    """Send one branded letter to a member. Returns (sent, message for the owner)."""
    to = gw._text(member.get("email"))
    name = gw._text(member.get("full_name") or member.get("name"), "this member")
    if "@" not in to:
        return False, f"{name} has no email address. Add one on their profile, or use WhatsApp."
    if not ready():
        return False, "Email sending isn't switched on yet (RESEND_API_KEY on Render)."
    opted, token = member_flags(supabase, gym_id, [member["id"]]).get(member["id"], (False, None))
    if opted:
        return False, f"{name} unsubscribed from emails, so GymPulse won't email them. Use WhatsApp instead."
    b = brand()
    unsub = unsub_link(token)
    clean = no_emoji(subject)
    try:
        pid = send(to, clean, render_message(b, clean, body, unsub, button), no_emoji(body)
                   + (f"\n\n{button[0]}: {button[1]}" if button and button[1] else "")
                   + (f"\n\nUnsubscribe: {unsub}" if unsub else ""), b, unsub)
    except Exception as error:
        return False, str(error)
    try:
        import gympulse_followups as fu
        fu.log_message(supabase, gym_id, member["id"], "email", "out", no_emoji(body), clean, provider_id=pid)
    except Exception:
        pass
    return True, f"Email sent to {name} ({to})."


def email_letter(to, subject, body, attachments=None, button=None):
    """A branded letter to someone who isn't a member (the owner, a company's HR)."""
    b = brand()
    clean = no_emoji(subject)
    return send(to, clean, render_message(b, clean, body, "", button), no_emoji(body), b,
                attachments=attachments)


# ------------------------------------------------------------------ sending
def _resend_key():
    import gympulse_followups as fu
    return fu._secret("RESEND_API_KEY")


def ready():
    return bool(_resend_key())


def send(to, subject, html, text, b, unsub_url="", attachments=None):
    import requests
    key = _resend_key()
    if not key:
        raise RuntimeError("Email sending isn't switched on yet (RESEND_API_KEY on Render).")
    frm, reply = sender_for(b)
    payload = {"from": frm, "to": [to], "subject": subject, "html": html, "text": text}
    if reply:
        payload["reply_to"] = reply
    if unsub_url:
        payload["headers"] = {"List-Unsubscribe": f"<{unsub_url}>"}
    if attachments:      # [(filename, bytes)]
        payload["attachments"] = [{"filename": n, "content": base64.b64encode(d).decode()}
                                  for n, d in attachments]
    r = requests.post("https://api.resend.com/emails", json=payload, timeout=20,
                      headers={"Authorization": f"Bearer {key}"})
    if r.status_code >= 300:
        raise RuntimeError(f"Email was not sent ({r.status_code}): {r.text[:200]}")
    return r.json().get("id", "")


def member_flags(supabase, gym_id, ids):
    """{member_id: (opted_out, unsub_token)} or {} before the SQL is run."""
    try:
        rows = (supabase.table("members").select("id, email_opt_out, unsub_token")
                .in_("id", list(ids)[:1000]).execute().data or [])
        return {r["id"]: (bool(r.get("email_opt_out")), r.get("unsub_token")) for r in rows}
    except Exception:
        return {}


def unsub_link(token):
    return f"{gw.APP_URL}/?unsub={token}" if token else ""


def banner_for(supabase, gym_id, fields, b, ctx, key):
    """Banner bytes plus a hosted URL (None when image hosting isn't set up)."""
    photo = _fetch_image(fields.get("photo_url") or b["photo_url"])
    logo = _fetch_image(b["logo_url"])
    png = make_banner(fill(fields["headline"], ctx), fill(fields.get("kicker", ""), ctx),
                      fill(fields.get("offer", ""), ctx), b["color"], b["dark"], photo, logo, b["gym"])
    url = upload_asset(supabase, gym_id, f"banners/{_slug(key)}.png", png)
    return png, url


# ------------------------------------------------------------------ UI: editor + preview
LINK_KINDS = {"whatsapp": "WhatsApp chat with the gym", "website": "Gym website",
              "reply": "Reply by email", "custom": "Custom link"}


def editor(prefix, template_name, b, ctx_preview):
    """Editable fields for one email; returns the field dict."""
    t = TEMPLATES[template_name]
    f = {}
    f["subject"] = st.text_input("Subject", t["subject"], key=f"{prefix}_subj_{template_name}")
    c1, c2 = st.columns(2)
    f["headline"] = c1.text_area("Banner headline", t["headline"], height=78, key=f"{prefix}_hl_{template_name}",
                                 help="Two short lines work best, e.g. COME / BACK.")
    f["kicker"] = c2.text_input("Banner tagline", t["kicker"], key=f"{prefix}_kk_{template_name}")
    f["offer"] = c2.text_input("Offer (optional)", "", key=f"{prefix}_of_{template_name}",
                               placeholder="e.g. 30% off any subscription",
                               help="Only shown if you type one. GymPulse never invents offers.")
    f["terms"] = ""
    if f["offer"]:
        f["terms"] = st.text_input("Offer terms (optional)", "", key=f"{prefix}_tm_{template_name}",
                                   placeholder="e.g. Valid until 30 November for returning members")
    body = st.text_area("Message", "\n\n".join(t["body"]), height=170, key=f"{prefix}_bd_{template_name}",
                        help="Use {first} for their first name and {gym} for your gym. Blank lines start new paragraphs.")
    f["body"] = [p.strip() for p in body.split("\n\n")]
    c3, c4 = st.columns(2)
    f["button"] = c3.text_input("Button text", t["button"], key=f"{prefix}_bt_{template_name}")
    kinds = list(LINK_KINDS)
    f["link"] = c4.selectbox("Button opens", kinds, index=kinds.index(t["link"]), format_func=LINK_KINDS.get,
                             key=f"{prefix}_lk_{template_name}")
    f["custom_link"] = st.text_input("Link", "", key=f"{prefix}_cl_{template_name}") if f["link"] == "custom" else ""
    themes = ["light", "dark"]
    f["theme"] = st.radio("Email background", themes, horizontal=True,
                          index=themes.index(b.get("email_theme", "light")),
                          format_func=lambda v: "White" if v == "light" else "Black",
                          key=f"{prefix}_th_{template_name}_{b.get('email_theme', 'light')}")
    f["preheader"] = t["preheader"]
    f["signoff"] = "{owner}\n{gym}"
    return f


def preview(fields, b, ctx, png):
    import streamlit.components.v1 as components
    uri = "data:image/png;base64," + base64.b64encode(png).decode() if png else ""
    html = render_email(fields, b, ctx, uri, unsub_url="#")
    components.html(html, height=900, scrolling=True)


# ------------------------------------------------------------------ UI: one member
def render_single(supabase, gym_id, member, play, details=None):
    """Branded email to one member from Follow-ups. Returns True when sent."""
    b = brand()
    name = template_for(play)
    names = list(TEMPLATES)
    name = st.selectbox("Email design", names, index=names.index(name), key=f"be_tpl_{name}")
    extra = dict(details or {})
    ctx = member_ctx(member, b, extra)
    trainer, show_card = None, True
    if name in TRAINER_TEMPLATES:
        trainer, show_card = trainer_picker("be", name, gw.load_trainers(supabase, gym_id),
                                            extra.get("trainer_id")) or (None, True)
        if trainer:
            ctx["trainer"] = gw._text(trainer.get("full_name"), ctx["trainer"])
    fields = editor("be", name, b, ctx)
    ctx = attach_trainer(fields, ctx, trainer, show_card)
    png = make_banner(fill(fields["headline"], ctx), fill(fields["kicker"], ctx), fill(fields["offer"], ctx),
                      b["color"], b["dark"], _fetch_image(b["photo_url"]), _fetch_image(b["logo_url"]), b["gym"])
    with st.expander("Preview", expanded=True):
        preview(fields, b, ctx, png)
    frm, reply = sender_for(b)
    st.caption(f"From **{frm}**" + (f" · replies go to **{reply}**" if reply else
                                     " · add your company email in Settings → Email & branding so replies reach you")
               + f" · {'Black' if fields['theme'] == 'dark' else 'White'} background")
    if not member.get("email"):
        st.warning("This member has no email address yet. Add one on their profile.")
        return False
    flags = member_flags(supabase, gym_id, [member["id"]])
    opted, token = flags.get(member["id"], (False, None))
    if opted:
        st.warning("This member unsubscribed from emails, so GymPulse won't email them.")
        return False
    if not ready():
        st.info("Email sending isn't switched on yet. Ask your GymPulse admin to add RESEND_API_KEY on Render.")
        return False
    if st.button("Send branded email", type="primary", key="be_send", use_container_width=True):
        try:
            url = upload_asset(supabase, gym_id, f"banners/{_slug(name)}-{member['id'][:8]}.png", png)
            host_trainer_photo(supabase, gym_id, fields)
            unsub = unsub_link(token)
            html = render_email(fields, b, ctx, url, unsub)
            subject = fill(fields["subject"], ctx)
            pid = send(member["email"], subject, html, plain_text(fields, ctx, unsub), b, unsub)
        except Exception as error:
            st.error(str(error))
            return False
        import gympulse_followups as fu
        fu.log_message(supabase, gym_id, member["id"], "email", "out", plain_text(fields, ctx), subject,
                       provider_id=pid)
        return True
    return False


def template_for(play):
    return PLAY_TO_TEMPLATE.get(play or "", "WhatsApp check-in")


# ------------------------------------------------------------------ UI: campaigns
AUDIENCES = {
    "lapsed": "Lapsed in the last 60 days (win back)",
    "away": "Not seen for 14+ days",
    "high": "High risk right now",
    "renewing": "Renewing in the next 14 days",
    "active": "All active members",
}


def audience(roster, key):
    if roster.empty:
        return roster
    end = pd.to_datetime(roster.get("membership_end"), errors="coerce") if "membership_end" in roster.columns else None
    today = pd.Timestamp(gw.today_local())
    if key == "lapsed" and end is not None:
        days = (today - end).dt.days
        return roster[(days > 0) & (days <= 60)]
    if key == "away":
        return roster[roster["days_since_last_visit"] >= 14]
    if key == "high":
        return roster[roster["risk_category"] == "High"]
    if key == "renewing":
        return roster[roster["renewal_due_days"].between(0, 14)]
    return roster


def render_campaigns(supabase, gym_id, roster):
    b = brand()
    st.markdown('<div class="section-label">EMAIL CAMPAIGN</div>', unsafe_allow_html=True)
    st.caption("Send one designed email to a group of members. Each email is personalised with their first "
               "name, and members who unsubscribed or have no email are skipped.")
    flash = st.session_state.pop("camp_flash", None)
    if flash:
        st.success(flash)
    if roster.empty:
        st.info("Add members first.")
        return
    c1, c2 = st.columns(2)
    aud = c1.selectbox("Who gets it", list(AUDIENCES), format_func=AUDIENCES.get, key="camp_aud")
    names = list(TEMPLATES)
    default = {"lapsed": "Win-back", "away": "WhatsApp check-in", "high": "Personal call",
               "renewing": "Renewal offer", "active": "Group challenge"}[aud]
    tname = c2.selectbox("Email design", names, index=names.index(default), key=f"camp_tpl_{aud}")
    group = audience(roster, aud)
    with_email = group[group["email"].fillna("").astype(str).str.contains("@")] if len(group) else group
    flags = member_flags(supabase, gym_id, with_email["id"]) if len(with_email) else {}
    sendable = with_email[[not flags.get(i, (False, None))[0] for i in with_email["id"]]] if len(with_email) else with_email
    st.write(f"**{len(sendable)}** member(s) will get this email"
             + (f" · {len(group) - len(with_email)} have no email" if len(group) != len(with_email) else "")
             + (f" · {len(with_email) - len(sendable)} unsubscribed" if len(with_email) != len(sendable) else "") + ".")
    sample = sendable.iloc[0] if len(sendable) else (group.iloc[0] if len(group) else roster.iloc[0])
    ctx = member_ctx(gw.member_message_ctx(sample), b)
    trainer, show_card = None, True
    if tname in TRAINER_TEMPLATES:
        trainer, show_card = trainer_picker(f"camp_{aud}", tname, gw.load_trainers(supabase, gym_id)) or (None, True)
        if trainer:
            ctx["trainer"] = gw._text(trainer.get("full_name"), ctx["trainer"])
    fields = editor(f"camp_{aud}", tname, b, ctx)
    ctx = attach_trainer(fields, ctx, trainer, show_card)
    png = make_banner(fill(fields["headline"], ctx), fill(fields["kicker"], ctx), fill(fields["offer"], ctx),
                      b["color"], b["dark"], _fetch_image(b["photo_url"]), _fetch_image(b["logo_url"]), b["gym"])
    with st.expander(f"Preview (as {ctx['first']} sees it)", expanded=True):
        preview(fields, b, ctx, png)
    frm, reply = sender_for(b)
    st.caption(f"From **{frm}**" + (f" · replies go to **{reply}**" if reply else "")
               + f" · {'Black' if fields['theme'] == 'dark' else 'White'} background")
    if not ready():
        st.info("Email sending isn't switched on yet (RESEND_API_KEY on Render).")
        return
    if not len(sendable):
        return
    sure = st.checkbox(f"Yes, send this email to {len(sendable)} member(s)", key=f"camp_ok_{aud}")
    if st.button("Send campaign", type="primary", key="camp_send", disabled=not sure, use_container_width=True):
        url = upload_asset(supabase, gym_id, f"banners/campaign-{_slug(tname)}.png", png)
        host_trainer_photo(supabase, gym_id, fields)
        import gympulse_followups as fu
        bar = st.progress(0.0, text="Sending…")
        sent = failed = 0
        for i, (_, r) in enumerate(sendable.iterrows(), 1):
            mctx = with_trainer(member_ctx(gw.member_message_ctx(r), b), fields)
            token = flags.get(r["id"], (False, None))[1]
            unsub = unsub_link(token)
            subject = fill(fields["subject"], mctx)
            try:
                pid = send(r["email"], subject, render_email(fields, b, mctx, url, unsub),
                           plain_text(fields, mctx, unsub), b, unsub)
                fu.log_message(supabase, gym_id, r["id"], "email", "out", plain_text(fields, mctx), subject,
                               provider_id=pid)
                row = gw.open_action_for(supabase, r["id"])
                if row:
                    gw.mark_contacted(supabase, row["id"], "Email", play=row.get("action_type"))
                sent += 1
            except Exception:
                failed += 1
            bar.progress(i / len(sendable), text=f"Sent {sent} of {len(sendable)}")
            time.sleep(0.6)          # stay within the email service's rate limit
        gw.bump_data_version()
        st.session_state["camp_flash"] = (f"Campaign sent to {sent} member(s)."
                                          + (f" {failed} could not be sent." if failed else ""))
        st.rerun()


# ------------------------------------------------------------------ UI: settings
def _resend_admin():
    import gympulse_followups as fu
    return fu._secret("RESEND_ADMIN_KEY")


def _resend_api(method, path, payload=None):
    import requests
    key = _resend_admin()
    if not key:
        raise RuntimeError("Connecting your own domain needs RESEND_ADMIN_KEY on Render (a Resend key with full access).")
    r = requests.request(method, f"https://api.resend.com{path}", json=payload, timeout=20,
                         headers={"Authorization": f"Bearer {key}"})
    if r.status_code >= 300:
        raise RuntimeError(f"Resend said {r.status_code}: {r.text[:200]}")
    return r.json() if r.text else {}


def render_brand_settings(supabase, gym_id, save):
    profile = st.session_state.get("user_profile") or {}
    s = dict(profile.get("settings") or {})
    cur = dict(s.get("email_brand") or {})
    b = brand(profile)
    st.markdown("**How your emails look and who they come from**")
    c1, c2 = st.columns(2)
    sender_name = c1.text_input("Sender name", b["sender_name"], placeholder="e.g. Emmanuel from GymPulse AI",
                                help="Shown as the sender in your members' inbox.")
    company_email = c2.text_input("Company email (replies go here)", b["company_email"],
                                  placeholder="e.g. hello@company.com")
    c3, c4, c5 = st.columns([1, 1, 2])
    color = c3.color_picker("Brand colour", b["color"])
    dark = c4.color_picker("Banner background", b["dark"])
    website = c5.text_input("Website (optional)", b["website"])
    c6, c7 = st.columns(2)
    whatsapp = c6.text_input("WhatsApp number for buttons", b["whatsapp"], placeholder="e.g. 0803 000 0000")
    address = c7.text_input("Address for the email footer", b["address"], placeholder="e.g. 12 Admiralty Way, Lekki, Lagos")
    email_theme = st.radio("Email background", ["light", "dark"], horizontal=True,
                           index=0 if b["email_theme"] == "light" else 1,
                           format_func=lambda v: "White" if v == "light" else "Black",
                           help="The default for every email. You can change it on any single email or campaign.",
                           key="eb_theme")
    if email_theme != b["email_theme"] and st.session_state.get("eb_theme_tried") != email_theme:
        st.session_state["eb_theme_tried"] = email_theme
        save({"settings": {**s, "email_brand": {**cur, "email_theme": email_theme}}},
             "Email background saved: " + ("Black." if email_theme == "dark" else "White."))
    u1, u2 = st.columns(2)
    logo_file = u1.file_uploader("Logo (PNG with transparent background is best)", type=["png", "jpg", "jpeg", "webp"],
                                 key="eb_logo")
    photo_file = u2.file_uploader("Gym photo for banners", type=["png", "jpg", "jpeg", "webp", "heic"], key="eb_photo")
    if b["logo_url"] or b["photo_url"]:
        st.caption("Saved: " + " · ".join(x for x in ["logo" if b["logo_url"] else "", "gym photo" if b["photo_url"] else ""] if x))
    if st.button("Save email branding", type="primary", key="eb_save"):
        new = {**cur, "sender_name": sender_name.strip(), "company_email": company_email.strip(),
               "color": color, "dark": dark, "website": website.strip(), "whatsapp": whatsapp.strip(),
               "address": address.strip(), "email_theme": email_theme}
        problems = []
        for f, key, name in ((logo_file, "logo_url", "logo"), (photo_file, "photo_url", "photo")):
            if f is not None:
                data, ctype = f.getvalue(), f.type or "image/png"
                if name == "photo":
                    try:
                        from PIL import Image, ImageOps
                        im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
                        im.thumbnail((1600, 1600))
                        buf = io.BytesIO(); im.save(buf, "JPEG", quality=86); data, ctype = buf.getvalue(), "image/jpeg"
                    except Exception:
                        pass
                url = upload_asset(supabase, gym_id, f"brand/{name}.{'jpg' if ctype == 'image/jpeg' else 'png'}",
                                   data, ctype)
                if url:
                    new[key] = url
                else:
                    problems.append(name)
        save({"settings": {**s, "email_brand": new}},
             "Email branding saved." + (f" Couldn't upload your {' and '.join(problems)}: run sql/gym_email.sql "
                                         "in Supabase to switch on image hosting." if problems else ""))
    st.markdown("**Preview**")
    ctx = member_ctx({"name": "Ada Obi", "goal": "Weight loss", "renew_days": 6}, b)
    t = dict(TEMPLATES["Win-back"]); t["theme"] = email_theme
    png = make_banner(t["headline"], t["kicker"], "", b["color"], b["dark"], _fetch_image(b["photo_url"]),
                      _fetch_image(b["logo_url"]), b["gym"])
    preview(t, b, ctx, png)

    st.markdown("**Send from your own email address**")
    frm, reply = sender_for(b)
    st.write(f"Right now your emails come from **{frm}**" + (f", and replies go to **{reply}**." if reply else "."))
    st.caption("To send from your own address (for example hello@company.com), connect your domain. "
               "You'll add three DNS records where your domain is managed, the same way GymPulse AI did.")
    d1, d2 = st.columns(2)
    domain = d1.text_input("Your domain", b["domain"], placeholder="e.g. company.com", key="eb_domain")
    sender_email = d2.text_input("Send from", b["sender_email"], placeholder="e.g. hello@company.com", key="eb_sender")
    a1, a2 = st.columns(2)
    if a1.button("Connect domain", key="eb_connect", use_container_width=True, disabled=not domain.strip()):
        try:
            res = _resend_api("POST", "/domains", {"name": domain.strip().lower()})
            new = {**cur, "domain": domain.strip().lower(), "domain_id": res.get("id", ""),
                   "domain_status": res.get("status", "pending"), "sender_email": sender_email.strip(),
                   "domain_records": res.get("records", [])}
            save({"settings": {**s, "email_brand": new}}, "Domain added. Now add the DNS records below.")
        except Exception as error:
            st.error(str(error))
    if b["domain_id"] and a2.button("Check verification", key="eb_verify", use_container_width=True):
        try:
            _resend_api("POST", f"/domains/{b['domain_id']}/verify")
            res = _resend_api("GET", f"/domains/{b['domain_id']}")
            new = {**cur, "domain_status": res.get("status", ""), "domain_records": res.get("records", []),
                   "sender_email": sender_email.strip() or cur.get("sender_email", "")}
            save({"settings": {**s, "email_brand": new}},
                 "Verified! Your emails now come from your own address." if res.get("status") == "verified"
                 else f"Status: {res.get('status', 'pending')}. DNS changes can take up to a few hours.")
        except Exception as error:
            st.error(str(error))
    recs = cur.get("domain_records") or []
    if recs:
        st.dataframe(pd.DataFrame([{"Type": r.get("type") or r.get("record"), "Name": r.get("name"),
                                    "Value": r.get("value"), "Priority": r.get("priority") or "",
                                    "Status": r.get("status")} for r in recs]),
                     hide_index=True, use_container_width=True)
        st.caption(f"Domain status: **{b['domain_status'] or 'pending'}**")


# ------------------------------------------------------------------ public: unsubscribe
def render_unsubscribe(supabase, token):
    import gympulse_booking as gb
    gb._header()
    _, col, _ = st.columns([1, 3, 1])
    with col:
        if st.session_state.get("unsub_done"):
            st.success(f"You're unsubscribed. {st.session_state['unsub_done']} won't send you any more emails.")
            return
        gw._md('<div class="bk-title">Unsubscribe</div>'
               '<div class="bk-sub">Stop receiving emails from your gym through GymPulse AI.</div>')
        if st.button("Unsubscribe me", type="primary", key="unsub_go"):
            try:
                rows = supabase.rpc("email_unsubscribe", {"p_token": str(token)}).execute().data or []
            except Exception:
                rows = []
            if not rows:
                st.error("This link isn't valid any more. Reply to the email and ask to be removed.")
                return
            r = rows[0] if isinstance(rows, list) else rows
            st.session_state["unsub_done"] = (r.get("business_name") if isinstance(r, dict) else None) or "Your gym"
            st.rerun()
