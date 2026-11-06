"""GymPulse AI · Community engagement: what makes members open the app at the gym.

  * "I'm at the gym" check-in posts and who's training now
  * weekly streaks with one free freeze a month (worked out from real check-ins)
  * gym challenges (progress from check-ins, badges and a shout-out when done)
  * workout buddies (goal and usual training time, "Train together?")
  * recognition: member of the week, coach replies, milestone and monthly recap cards
  * class feeds (photos from class, tag classmates)
  * progress posts (PB, before / after)
  * smart nudges, polls and "Ask the coach"
  * branded stickers and frames on photos (the gym's name, ready for Instagram)
Database: sql/phase24_community_engage.sql. Used by gympulse_community.
"""
import io
import os
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

WORKOUTS = ["Legs", "Push", "Pull", "Full body", "Upper body", "Core", "Cardio", "Class", "Stretch & mobility", "Other"]
GOALS = ["Weight loss", "Muscle gain", "General fitness", "Strength", "Endurance", "Sports performance"]
TIMES = {"early": "Early (before 8am)", "midday": "Midday", "evening": "Evening (after 5pm)", "weekend": "Weekends"}
STICKERS = ["", "Leg day ✅", "New PB 🏆", "Cardio done", "Early bird ☀️", "Back at it 💪", "Rest day earned"]
MILESTONES = [10, 25, 50, 100, 200, 300, 500, 1000]
KIND_LABEL = {"checkin": "📍 At the gym", "progress": "📈 Progress", "milestone": "🏅 Milestone",
              "recognition": "⭐ Member of the week", "challenge": "🏆 Challenge", "poll": "📊 Poll",
              "question": "❓ Question for the coach", "class": "🧘 Class"}
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")


def ready(sc):
    try:
        sc.table("community_challenges").select("id").limit(1).execute()
        return True
    except Exception:
        return False


# ------------------------------------------------------------------ visits, streaks, training now
def visit_times(sc, gym_id, member_id, days=420):
    """Local check-in datetimes for one member (newest first)."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        rows = gw.fetch_all(sc.table("checkins").select("checked_in_at").eq("gym_id", gym_id)
                            .eq("member_id", member_id).gte("checked_in_at", since).order("checked_in_at", desc=True))
    except Exception:
        rows = []
    at = pd.to_datetime(pd.Series([r.get("checked_in_at") for r in rows], dtype=object), errors="coerce", utc=True,
                        format="ISO8601").dropna()
    return [t.tz_convert(gw.APP_TZ).to_pydatetime() for t in at]


def streak(days, today=None):
    """Weekly streak from visit dates: weeks in a row (Mon–Sun) with a visit. A missed week is covered by a
    freeze, at most one a calendar month. The current week doesn't break it until it's over.
    Returns {"weeks", "freeze_left", "this_week", "at_risk", "frozen"}."""
    today = today or gw.today_local()
    weeks = {d - timedelta(days=d.weekday()) for d in days}
    wk = today - timedelta(days=today.weekday())
    this_week = wk in weeks
    used = {}
    count, frozen = 0, 0
    cur = wk if this_week else wk - timedelta(days=7)
    for _ in range(260):
        if cur in weeks:
            count += 1
        else:
            month = (cur.year, cur.month)
            if count and used.get(month, 0) < 1 and (cur - timedelta(days=7)) in weeks:
                used[month] = used.get(month, 0) + 1
                frozen += 1
            else:
                break
        cur -= timedelta(days=7)
    month_now = (today.year, today.month)
    return {"weeks": count, "freeze_left": 0 if used.get(month_now) else 1, "this_week": this_week,
            "at_risk": count > 0 and not this_week and today.weekday() >= 3, "frozen": frozen}


def training_now(sc, gym_id, hours=2):
    """{member_id: check-in time} for check-ins in the last few hours."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    try:
        rows = sc.table("checkins").select("member_id, checked_in_at").eq("gym_id", gym_id) \
            .gte("checked_in_at", since).execute().data or []
    except Exception:
        return {}
    return {r["member_id"]: r["checked_in_at"] for r in rows if r.get("member_id")}


def trained_today(sc, gym_id):
    start = datetime.combine(gw.today_local(), datetime.min.time()).replace(tzinfo=gw.APP_TZ)
    try:
        rows = sc.table("checkins").select("member_id").eq("gym_id", gym_id) \
            .gte("checked_in_at", start.isoformat()).execute().data or []
    except Exception:
        return set()
    return {r["member_id"] for r in rows if r.get("member_id")}


# ------------------------------------------------------------------ images: stickers, frames, cards
def _font(size, bold=True):
    from PIL import ImageFont
    for name in (["InterDisplay-Black.otf", "InterDisplay-Bold.otf"] if bold else ["Inter-SemiBold.otf", "Inter-Medium.otf"]):
        try:
            return ImageFont.truetype(os.path.join(FONT_DIR, name), size)
        except Exception:
            continue
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _clean(text):
    """Pillow fonts here have no colour emoji: keep the words, drop symbols they can't draw."""
    return "".join(ch for ch in str(text or "") if ord(ch) < 0x2100 or ch in "–—’").strip()


def _jpeg(img, q=82):
    out = io.BytesIO()
    img.convert("RGB").save(out, format="JPEG", quality=q, optimize=True)
    return out.getvalue()


def _gradient(w, h, a=(183, 243, 74), b=(53, 211, 232)):
    from PIL import Image
    g = Image.new("RGB", (w, h))
    px = g.load()
    for y in range(h):
        for x in range(0, w, 4):
            t = (x / w * 0.6 + y / h * 0.4)
            c = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
            for dx in range(4):
                if x + dx < w:
                    px[x + dx, y] = c
    return g


def frame_photo(raw_jpeg, gym_name, sticker="", frame=True):
    """Add a sticker (top left pill) and the gym's frame (bottom band with its name) to a photo."""
    from PIL import Image, ImageDraw
    img = Image.open(io.BytesIO(raw_jpeg)).convert("RGB")
    w, h = img.size
    d = ImageDraw.Draw(img, "RGBA")
    s = _clean(sticker)
    if s:
        f = _font(max(28, w // 22))
        tw = d.textlength(s, font=f)
        pad = w // 40
        box = (pad, pad, pad + tw + pad * 2.2, pad + f.size + pad * 1.6)
        d.rounded_rectangle(box, radius=f.size, fill=(183, 243, 74, 235))
        d.text((pad + pad * 1.1, pad + pad * 0.7), s, font=f, fill=(10, 15, 30))
    if frame:
        band = max(70, h // 11)
        d.rectangle((0, h - band, w, h), fill=(7, 11, 20, 215))
        f = _font(max(24, band // 2 - 4))
        name = _clean(gym_name).upper() or "MY GYM"
        d.text((band // 3, h - band + (band - f.size) // 2 - 2), name, font=f, fill=(255, 255, 255))
        g = _font(max(16, band // 4), bold=False)
        tag = "GymPulse AI"
        d.text((w - d.textlength(tag, font=g) - band // 3, h - band + (band - g.size) // 2), tag, font=g,
               fill=(183, 243, 74))
    return _jpeg(img)


def before_after(raw_a, raw_b, gym_name):
    from PIL import Image, ImageDraw, ImageOps
    a = ImageOps.fit(Image.open(io.BytesIO(raw_a)).convert("RGB"), (540, 720))
    b = ImageOps.fit(Image.open(io.BytesIO(raw_b)).convert("RGB"), (540, 720))
    out = Image.new("RGB", (1080, 720), (7, 11, 20))
    out.paste(a, (0, 0))
    out.paste(b, (540, 0))
    d = ImageDraw.Draw(out, "RGBA")
    f = _font(34)
    for x, label in ((24, "BEFORE"), (564, "AFTER")):
        d.rounded_rectangle((x, 24, x + d.textlength(label, font=f) + 36, 24 + 54), radius=27, fill=(183, 243, 74, 235))
        d.text((x + 18, 31), label, font=f, fill=(10, 15, 30))
    d.line((540, 0, 540, 720), fill=(7, 11, 20), width=6)
    return frame_photo(_jpeg(out), gym_name, "", True)


def card(title, big, sub, gym_name, w=1080, h=1350):
    """A shareable gradient card: milestones and monthly recaps."""
    from PIL import ImageDraw
    img = _gradient(w, h)
    d = ImageDraw.Draw(img, "RGBA")
    d.rounded_rectangle((60, 60, w - 60, h - 60), radius=56, fill=(7, 11, 20, 238))
    t = _font(46, bold=False)
    d.text((120, 150), _clean(title), font=t, fill=(183, 243, 74))
    bf = _font(260)
    big = _clean(big)
    d.text((120, 300), big, font=bf, fill=(255, 255, 255))
    sf = _font(58)
    y = 640
    for line in _wrap(_clean(sub), sf, w - 240, d):
        d.text((120, y), line, font=sf, fill=(244, 247, 251))
        y += 76
    nf = _font(44)
    d.text((120, h - 210), _clean(gym_name).upper(), font=nf, fill=(255, 255, 255))
    gf = _font(30, bold=False)
    d.text((120, h - 150), "Shared from the GymPulse AI member app", font=gf, fill=(147, 160, 180))
    return _jpeg(img, 88)


def _wrap(text, font, width, d):
    words, lines, cur = text.split(), [], ""
    for wd in words:
        trial = (cur + " " + wd).strip()
        if d.textlength(trial, font=font) <= width:
            cur = trial
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines[:5]


# ------------------------------------------------------------------ badges and challenges
def badges(sc, member_id):
    try:
        return sc.table("community_badges").select("*").eq("member_id", member_id).order("created_at", desc=True) \
            .execute().data or []
    except Exception:
        return []


def give_badge(sc, gym_id, member_id, ref, label):
    try:
        sc.table("community_badges").insert({"gym_id": gym_id, "member_id": member_id, "ref": ref,
                                             "label": label}).execute()
        return True
    except Exception:
        return False                                      # already has it


def challenges(sc, gym_id, live_only=True):
    try:
        q = sc.table("community_challenges").select("*").eq("gym_id", gym_id)
        if live_only:
            q = q.gte("ends_on", (gw.today_local() - timedelta(days=3)).isoformat())
        return q.order("ends_on").execute().data or []
    except Exception:
        return []


def entries(sc, gym_id, challenge_ids):
    if not challenge_ids:
        return []
    try:
        return sc.table("community_challenge_entries").select("*").eq("gym_id", gym_id) \
            .in_("challenge_id", list(challenge_ids)).execute().data or []
    except Exception:
        return []


def progress(days, ch):
    s, e = date.fromisoformat(str(ch["starts_on"])[:10]), date.fromisoformat(str(ch["ends_on"])[:10])
    return len({d for d in days if s <= d <= e})


def settle_challenges(sc, gym_id, member_id=None, gym_name=""):
    """Mark finished challenge entries complete: badge, notification and a gym shout-out post."""
    import gympulse_community as gcom
    chs = {c["id"]: c for c in challenges(sc, gym_id)}
    ents = [e for e in entries(sc, gym_id, chs) if not e.get("completed_at")
            and (member_id is None or e["member_id"] == member_id)]
    done = 0
    names = gcom.people(sc, gym_id)
    for e in ents:
        ch = chs[e["challenge_id"]]
        days = {t.date() for t in visit_times(sc, gym_id, e["member_id"], 120)}
        if progress(days, ch) < int(ch["goal_visits"]):
            continue
        now = datetime.now(timezone.utc).isoformat()
        sc.table("community_challenge_entries").update({"completed_at": now}).eq("challenge_id", ch["id"]) \
            .eq("member_id", e["member_id"]).execute()
        give_badge(sc, gym_id, e["member_id"], f"challenge:{ch['id']}", f"{ch.get('badge') or '🏆'} {ch['title']}")
        who = gw._text((names.get(e["member_id"]) or {}).get("full_name"), "A member")
        sc.table("community_posts").insert({
            "gym_id": gym_id, "member_id": None, "author_name": gym_name or "Your gym", "kind": "challenge",
            "body": f"{ch.get('badge') or '🏆'} Huge congratulations to {who} for completing \"{ch['title']}\": "
                    f"{ch['goal_visits']} visits! 👏",
            "meta": {"challenge_id": ch["id"], "member_id": e["member_id"], "done": True}}).execute()
        _note(sc, gym_id, e["member_id"], "badge", f"challenge:{ch['id']}")
        done += 1
    return done


def _note(sc, gym_id, member_id, kind, ref=None, actor_id=None):
    try:
        sc.table("community_notifications").insert({"gym_id": gym_id, "member_id": member_id, "actor_id": actor_id,
                                                    "kind": kind, "ref": ref,
                                                    "created_at": datetime.now(timezone.utc).isoformat()}).execute()
    except Exception:
        pass


# ------------------------------------------------------------------ member: top of the feed
def render_top(sc, m, gym_name, profile):
    """Nudges, who's training now, check-in share card, milestone / recap cards and live challenges."""
    import gympulse_community as gcom
    if not ready(sc):
        return
    times = visit_times(sc, m["gym_id"], m["id"])
    days = {t.date() for t in times}
    today = gw.today_local()
    settle_challenges(sc, m["gym_id"], m["id"], gym_name)
    _nudges(sc, m, days, today)
    if gcom.show_training_now(profile):
        _training_now(sc, m)
    _checkin_card(sc, m, gym_name, times, today)
    _milestone_cards(sc, m, gym_name, days, today)
    _challenges_strip(sc, m, gym_name, days)


def _nudges(sc, m, days, today):
    import gympulse_community as gcom
    msgs = []
    fol = gcom.following_of(sc, m["gym_id"], m["id"])
    if fol:
        n = len(fol & trained_today(sc, m["gym_id"]))
        if n:
            msgs.append(f"💪 {n} {'person' if n == 1 else 'people'} you follow trained today.")
    s = streak(days, today)
    if s["at_risk"]:
        sunday = today + timedelta(days=6 - today.weekday())
        msgs.append(f"🔥 Your {s['weeks']}-week streak ends {'today' if sunday == today else 'Sunday'}: one visit "
                    "keeps it going." + (" (Or your free freeze will cover this week.)" if s["freeze_left"] else ""))
    chs = {c["id"]: c for c in challenges(sc, m["gym_id"])}
    for e in entries(sc, m["gym_id"], chs):
        if e["member_id"] != m["id"] or e.get("completed_at"):
            continue
        ch = chs[e["challenge_id"]]
        left = int(ch["goal_visits"]) - progress(days, ch)
        end = date.fromisoformat(str(ch["ends_on"])[:10])
        if 0 < left and end >= today:
            msgs.append(f"🏆 {left} more visit{'s' if left != 1 else ''} to finish \"{ch['title']}\" "
                        f"({(end - today).days} day{'s' if (end - today).days != 1 else ''} left).")
    for t in msgs[:3]:
        gw._md(f'<div class="eg-nudge">{gw._esc(t)}</div>')


def _training_now(sc, m):
    import gympulse_community as gcom
    now = training_now(sc, m["gym_id"])
    pp = gcom.people(sc, m["gym_id"])
    ids = [i for i in now if i in pp and not pp[i].get("community_hide_now")]
    if not ids:
        return
    fol = gcom.following_of(sc, m["gym_id"], m["id"])
    ids.sort(key=lambda i: (i not in fol, i != m["id"]))
    faces = "".join(f'<span title="{gw._esc(pp[i].get("full_name"))}">'
                    f'{gw.avatar_html(pp[i].get("full_name"), pp[i].get("photo"), 30)}</span>' for i in ids[:7])
    gw._md(f'<div class="eg-now"><span class="eg-dot"></span><b>{len(ids)} training now</b>'
           f'<div class="eg-faces">{faces}</div></div>')


def _checkin_card(sc, m, gym_name, times, today):
    todays = [t for t in times if t.date() == today]
    if not todays or m.get("community_blocked"):
        return
    start = datetime.combine(today, datetime.min.time()).replace(tzinfo=gw.APP_TZ).isoformat()
    try:
        posted = sc.table("community_posts").select("id").eq("member_id", m["id"]).eq("kind", "checkin") \
            .gte("created_at", start).limit(1).execute().data
    except Exception:
        posted = []
    if posted or st.session_state.get("eg_ck_skip") == str(today):
        return
    t = min(todays)
    with st.container(border=True, key="eg_ck"):
        st.markdown(f"**📍 You checked in at {t:%I:%M %p}.** Let your gym know you're here?")
        with st.form("eg_ck_form", clear_on_submit=True, border=False):
            a, b = st.columns(2)
            wk = a.selectbox("Today's workout", WORKOUTS, key="eg_ck_w")
            stk = b.selectbox("Sticker", STICKERS, format_func=lambda s: s or "No sticker", key="eg_ck_s")
            note = st.text_input("Add a note (optional)", max_chars=200, placeholder="e.g. Trying the new HIIT class")
            ph = st.file_uploader("Photo (optional)", type=["jpg", "jpeg", "png", "webp", "heic", "heif"], key="eg_ck_p")
            go = st.form_submit_button("Share: I'm at the gym 💪", type="primary", use_container_width=True)
        if go:
            import gympulse_community as gcom
            pic = None
            if ph is not None:
                pic = gcom._store_photo(sc, m["gym_id"], frame_photo(gcom._image(ph.getvalue()), gym_name, stk))
            body = f"At the gym 💪 · {wk}" + (f"\n{note.strip()}" if note.strip() else "")
            sc.table("community_posts").insert({"gym_id": m["gym_id"], "member_id": m["id"],
                                                "author_name": gw._text(m.get("full_name"), "Member"),
                                                "kind": "checkin", "body": body, "photo": pic,
                                                "meta": {"workout": wk, "at": t.isoformat()}}).execute()
            st.session_state["cm_flash"] = "Shared. Have a great session!"
            st.rerun()
        if st.button("Not today", key="eg_ck_no", type="tertiary"):
            st.session_state["eg_ck_skip"] = str(today)
            st.rerun()


def _milestone_cards(sc, m, gym_name, days, today):
    have = {b["ref"] for b in badges(sc, m["id"])}
    offers = []
    total = len(days)
    reached = [n for n in MILESTONES if total >= n]
    if reached and f"visits:{max(reached)}" not in have:     # only the highest one reached, once
        n = max(reached)
        offers.append((f"visits:{n}", "MILESTONE", f"{n}", f"visits at {gym_name}. Every one counted.",
                       f"🏅 {n} visits at {gym_name}!"))
    since = pd.to_datetime(m.get("member_since") or m.get("created_at"), errors="coerce")
    if not pd.isna(since):
        years = (today - since.date()).days // 365
        if years >= 1 and f"year:{years}" not in have:
            offers.append((f"year:{years}", "ANNIVERSARY", f"{years}", f"year{'s' if years > 1 else ''} with "
                           f"{gym_name}. Thank you for showing up.", f"🎉 {years} year{'s' if years > 1 else ''} at {gym_name}!"))
    if today.day <= 7:
        first = today.replace(day=1)
        prev = (first - timedelta(days=1)).replace(day=1)
        n = len({d for d in days if prev <= d < first})
        ref = f"recap:{prev:%Y-%m}"
        if n and ref not in have:
            s = streak(days, today)
            offers.append((ref, f"YOUR {prev:%B}".upper(), f"{n}", f"times you trained in {prev:%B}."
                           + (f" {s['weeks']}-week streak and counting." if s["weeks"] > 1 else ""),
                           f"📅 I trained {n} times in {prev:%B} at {gym_name}"))
    for ref, title, big, sub, caption in offers[:1]:
        with st.container(border=True, key=f"eg_ms_{ref.replace(':', '_')}"):
            img = card(title, big, sub, gym_name)
            import base64
            gw._md(f'<img class="cm-img" src="data:image/jpeg;base64,{base64.b64encode(img).decode()}" alt="">')
            a, b, c = st.columns([1.4, 1.2, 1])
            if a.button("Share to feed", key=f"eg_ms_share_{ref}", type="primary", use_container_width=True):
                import gympulse_community as gcom
                url = gcom._store_photo(sc, m["gym_id"], img)
                give_badge(sc, m["gym_id"], m["id"], ref, caption)
                sc.table("community_posts").insert({"gym_id": m["gym_id"], "member_id": m["id"],
                                                    "author_name": gw._text(m.get("full_name"), "Member"),
                                                    "kind": "milestone", "body": caption, "photo": url,
                                                    "meta": {"ref": ref}}).execute()
                st.session_state["cm_flash"] = "Shared. Well done!"
                st.rerun()
            b.download_button("Save image", img, f"gympulse-{ref.replace(':', '-')}.jpg", "image/jpeg",
                              key=f"eg_ms_dl_{ref}", use_container_width=True)
            if c.button("Not now", key=f"eg_ms_no_{ref}", use_container_width=True):
                give_badge(sc, m["gym_id"], m["id"], ref, caption)
                st.rerun()


def _challenges_strip(sc, m, gym_name, days):
    chs = [c for c in challenges(sc, m["gym_id"]) if date.fromisoformat(str(c["ends_on"])[:10]) >= gw.today_local()]
    if not chs:
        return
    ents = entries(sc, m["gym_id"], [c["id"] for c in chs])
    mine = {e["challenge_id"]: e for e in ents if e["member_id"] == m["id"]}
    for ch in chs[:3]:
        n = sum(1 for e in ents if e["challenge_id"] == ch["id"])
        with st.container(border=True, key=f"eg_ch_{ch['id']}"):
            gw._md(f'<div class="eg-ch-t">{gw._esc(ch.get("badge") or "🏆")} {gw._esc(ch["title"])}</div>'
                   f'<div class="cm-when">{ch["goal_visits"]} visits · '
                   f'{pd.to_datetime(ch["starts_on"]):%d %b} – {pd.to_datetime(ch["ends_on"]):%d %b} · '
                   f'{n} joined</div>')
            e = mine.get(ch["id"])
            if e:
                p = min(progress(days, ch), int(ch["goal_visits"]))
                st.progress(p / int(ch["goal_visits"]),
                            text="Completed! 🎉" if e.get("completed_at") else f"{p} of {ch['goal_visits']} visits")
            elif st.button("Join the challenge", key=f"eg_join_{ch['id']}", type="primary"):
                try:
                    sc.table("community_challenge_entries").insert({"challenge_id": ch["id"], "gym_id": m["gym_id"],
                                                                    "member_id": m["id"]}).execute()
                    sc.table("community_posts").insert({
                        "gym_id": m["gym_id"], "member_id": m["id"], "author_name": gw._text(m.get("full_name"), "Member"),
                        "kind": "challenge", "body": f"I just joined \"{ch['title']}\" ({ch['goal_visits']} visits). Who's with me?",
                        "meta": {"challenge_id": ch["id"]}}).execute()
                except Exception:
                    pass
                st.session_state["cm_flash"] = "You're in. Every check-in counts!"
                st.rerun()


# ------------------------------------------------------------------ member: composer extras
def composer(sc, m, gym_name, key="cm_new", class_id=None, classmates=None):
    """Post composer with type (post / progress / ask the coach), before/after, sticker and frame."""
    import gympulse_community as gcom
    eng = ready(sc)
    with st.form(key, clear_on_submit=True, border=False):
        kind = "post"
        if eng and not class_id:
            kind = st.segmented_control("Type", ["post", "progress", "question"], default="post",
                                        format_func={"post": "Post", "progress": "📈 Progress",
                                                     "question": "❓ Ask the coach"}.get,
                                        key=f"{key}_kind", label_visibility="collapsed") or "post"
        body = st.text_area("Share something with your gym", max_chars=gcom.MAX_BODY, label_visibility="collapsed",
                            placeholder="Photos from class? Tag your classmates 📸" if class_id else
                            "New personal best? A class you loved? Say hi 👋")
        photo = st.file_uploader("Photo (optional)", type=["jpg", "jpeg", "png", "webp", "heic", "heif"], key=f"{key}_p")
        after = None
        sticker, frame, tags = "", False, []
        if eng:
            with st.container(key=f"{key}_opts"):
                c1, c2 = st.columns(2)
                sticker = c1.selectbox("Sticker", STICKERS, format_func=lambda s: s or "No sticker", key=f"{key}_s")
                frame = c2.toggle(f"{gym_name} frame", value=False, key=f"{key}_f")
            if not class_id:
                after = st.file_uploader("Progress: add an 'after' photo for a before / after (optional)",
                                         type=["jpg", "jpeg", "png", "webp", "heic", "heif"], key=f"{key}_a")
            if classmates:
                tags = st.multiselect("Tag classmates", list(classmates), format_func=lambda i: classmates[i],
                                      key=f"{key}_t", max_selections=10)
        go = st.form_submit_button("Post", type="primary", use_container_width=True)
    if not go:
        return
    if not body.strip() and photo is None:
        st.error("Write something or add a photo.")
        return
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    try:
        today = sc.table("community_posts").select("id").eq("member_id", m["id"]).gte("created_at", since) \
            .execute().data or []
    except Exception:
        today = []
    if len(today) >= gcom.POSTS_PER_DAY:
        st.error("That's a lot of posts today. Please try again tomorrow.")
        return
    pic = None
    try:
        if photo is not None and after is not None:
            pic = gcom._store_photo(sc, m["gym_id"], before_after(gcom._image(photo.getvalue()),
                                                                  gcom._image(after.getvalue()), gym_name))
            kind = "progress"
        elif photo is not None:
            raw = gcom._image(photo.getvalue())
            if sticker or frame:
                raw = frame_photo(raw, gym_name, sticker, frame)
            pic = gcom._store_photo(sc, m["gym_id"], raw)
    except Exception:
        st.error("That photo couldn't be read. Try a JPG or PNG.")
        return
    row = {"gym_id": m["gym_id"], "member_id": m["id"], "author_name": gw._text(m.get("full_name"), "Member"),
           "body": body.strip()[:gcom.MAX_BODY], "photo": pic}
    if eng:
        row.update({"kind": "class" if class_id else kind, "class_id": class_id,
                    "meta": {"tags": tags} if tags else None})
    res = sc.table("community_posts").insert(row).execute().data or []
    for t in tags:
        _note(sc, m["gym_id"], t, "tag", (res[0] if res else {}).get("id"), m["id"])
    st.session_state["cm_flash"] = "Posted."
    st.rerun()


# ------------------------------------------------------------------ member: post extras
def post_label(sc, m, p):
    """The post's kind (check-in, progress, poll…) and who's tagged, above the text."""
    import gympulse_community as gcom
    kind = p.get("kind") or "post"
    if kind in KIND_LABEL:
        gw._md(f'<span class="eg-kind eg-{kind}">{KIND_LABEL[kind]}</span>')
    tags = (p.get("meta") or {}).get("tags") or []
    if tags:
        pp = gcom.people(sc, m["gym_id"])
        names = ", ".join(gw._esc(gw._text((pp.get(t) or {}).get("full_name"), "Member")) for t in tags)
        gw._md(f'<div class="cm-when">with {names}</div>')


def post_poll(sc, m, p):
    meta = p.get("meta") or {}
    if p.get("kind") == "poll" and meta.get("options"):
        _poll(sc, m, p, meta["options"])


def _poll(sc, m, p, options):
    try:
        votes = sc.table("community_poll_votes").select("member_id, choice").eq("post_id", p["id"]).execute().data or []
    except Exception:
        votes = []
    mine = next((v["choice"] for v in votes if v["member_id"] == m.get("id")), None)
    total = len(votes)
    for i, opt in enumerate(options[:4]):
        n = sum(1 for v in votes if v["choice"] == i)
        if mine is None and m.get("id"):
            if st.button(opt, key=f"eg_vote_{p['id']}_{i}", use_container_width=True):
                try:
                    sc.table("community_poll_votes").insert({"post_id": p["id"], "gym_id": p["gym_id"],
                                                             "member_id": m["id"], "choice": i}).execute()
                except Exception:
                    pass
                st.rerun()
        else:
            pct = round(100 * n / total) if total else 0
            gw._md(f'<div class="eg-bar{" me" if mine == i else ""}"><i style="width:{pct}%"></i>'
                   f'<span>{gw._esc(opt)}</span><b>{pct}%</b></div>')
    gw._md(f'<div class="cm-when">{total} vote{"s" if total != 1 else ""}</div>')


# ------------------------------------------------------------------ member: profile extras
def profile_extras(sc, m, pid):
    if not ready(sc):
        return
    days = {t.date() for t in visit_times(sc, m["gym_id"], pid)}
    s = streak(days)
    bs = badges(sc, pid)
    chips = []
    if s["weeks"]:
        chips.append(f'🔥 {s["weeks"]}-week streak')
    chips += [gw._esc(b["label"]) for b in bs[:6]]
    if chips:
        gw._md('<div class="eg-chips">' + "".join(f'<span>{c}</span>' for c in chips) + "</div>")
    if pid == m["id"] and s["weeks"]:
        st.caption(f"Train at least once a week to keep your streak. "
                   f"{'You have 1 free freeze this month for a missed week.' if s['freeze_left'] else 'Your free freeze for this month is used.'}")


# ------------------------------------------------------------------ member: buddies
def render_buddies(sc, m, gym_name):
    import gympulse_community as gcom
    if not ready(sc):
        st.caption("Workout buddies are coming soon.")
        return
    me = gcom.people(sc, m["gym_id"]).get(m["id"], m)
    with st.expander("My buddy profile", icon=":material/handshake:", expanded=not me.get("buddy_open")):
        with st.form("eg_buddy", border=False):
            on = st.toggle("Show me in Find a buddy", value=bool(me.get("buddy_open")))
            goal_now = me.get("buddy_goal") or gw._text(m.get("fitness_goal")) or GOALS[2]
            goal = st.selectbox("My goal", GOALS, index=GOALS.index(goal_now) if goal_now in GOALS else 2)
            times = st.multiselect("When I usually train", list(TIMES), format_func=TIMES.get,
                                   default=[t for t in gw._text(me.get("buddy_times")).split(",") if t in TIMES])
            note = st.text_input("A line about you (optional)", value=gw._text(me.get("buddy_note")), max_chars=120,
                                 placeholder="e.g. Beginner, would love a gym partner for leg day")
            if st.form_submit_button("Save", type="primary"):
                sc.table("members").update({"buddy_open": bool(on), "buddy_goal": goal, "buddy_times": ",".join(times),
                                            "buddy_note": note.strip() or None}).eq("id", m["id"]).execute()
                gcom._bust(m["gym_id"])
                st.session_state["cm_flash"] = "Buddy profile saved."
                st.rerun()
    try:
        rows = sc.table("members").select("id, full_name, photo, buddy_goal, buddy_times, buddy_note, community_agreed_at") \
            .eq("gym_id", m["gym_id"]).eq("buddy_open", True).execute().data or []
    except Exception:
        rows = []
    mine_b, theirs_b = gcom._blocks(sc, m["gym_id"], m["id"])
    my_goal, my_times = me.get("buddy_goal"), set(gw._text(me.get("buddy_times")).split(","))
    rows = [r for r in rows if r["id"] != m["id"] and r.get("community_agreed_at") and r["id"] not in mine_b | theirs_b]
    rows.sort(key=lambda r: -((r.get("buddy_goal") == my_goal) * 2
                              + len(my_times & set(gw._text(r.get("buddy_times")).split(",")) - {""})))
    if not rows:
        st.caption("Nobody has a buddy profile yet. Switch yours on so others can find you.")
        return
    st.markdown('<div class="section-label">FIND A BUDDY</div>', unsafe_allow_html=True)
    for r in rows[:30]:
        shared = my_times & set(gw._text(r.get("buddy_times")).split(",")) - {""}
        with st.container(border=True, key=f"eg_bd_{r['id']}"):
            a, b = st.container(key=f"cm_row_bd_{r['id']}").columns([1, 6], vertical_alignment="center")
            gw._md(gw.avatar_html(r.get("full_name"), r.get("photo"), 44), a)
            with b:
                st.button(gw._text(r.get("full_name"), "Member"), key=f"eg_bdp_{r['id']}", type="tertiary",
                          on_click=gcom._open_profile, args=(r["id"],))
                bits = [r.get("buddy_goal") or ""] + [TIMES[t].split(" (")[0] for t in gw._text(r.get("buddy_times")).split(",") if t in TIMES]
                gw._md(f'<div class="cm-when">{gw._esc(" · ".join(x for x in bits if x))}'
                       + (" · ✨ match" if r.get("buddy_goal") == my_goal or shared else "") + "</div>")
            if r.get("buddy_note"):
                gw._md(f'<div class="cm-c">{gw._esc(r["buddy_note"])}</div>')
            if st.button("Train together?", key=f"eg_bdm_{r['id']}", icon=":material/fitness_center:"):
                ok, why = gcom.can_message(sc, m, r)
                if not ok:
                    st.caption(why)
                else:
                    when = " / ".join(TIMES[t].split(" (")[0].lower() for t in my_times if t in TIMES) or "soon"
                    sc.table("community_dms").insert({
                        "gym_id": m["gym_id"], "sender_id": m["id"], "recipient_id": r["id"],
                        "body": f"Hey {(gw._text(r.get('full_name')).split() or [''])[0]}! I saw you in Find a buddy. "
                                f"Want to train together? I usually train {when}. 💪"}).execute()
                    gcom.notify(sc, m, r["id"], "message")
                    gcom._open_chat(r["id"])
                    st.rerun()


# ------------------------------------------------------------------ member: class feeds
def my_classes(sc, m):
    """Classes the member booked or attended in the last 14 days or booked in the next 7."""
    now = datetime.now(gw.APP_TZ).replace(tzinfo=None)
    cls = {str(c["id"]): c for c in gw._fetch_classes(sc, m["gym_id"])
           if now - timedelta(days=14) <= c["_start"] <= now + timedelta(days=7)}
    if not cls:
        return []
    mine = set()
    try:
        mine |= {str(b["class_id"]) for b in sc.table("class_bookings").select("class_id").eq("member_id", m["id"])
                 .execute().data or []}
    except Exception:
        pass
    try:
        mine |= {str(c["class_id"]) for c in sc.table("checkins").select("class_id").eq("member_id", m["id"])
                 .execute().data or [] if c.get("class_id")}
    except Exception:
        pass
    return sorted([cls[c] for c in mine if c in cls], key=lambda c: c["_start"], reverse=True)


def classmates(sc, m, class_id):
    import gympulse_community as gcom
    ids = set()
    for table, col in (("class_bookings", "member_id"), ("checkins", "member_id")):
        try:
            ids |= {r[col] for r in sc.table(table).select(col).eq("gym_id", m["gym_id"]).eq("class_id", class_id)
                    .execute().data or [] if r.get(col)}
        except Exception:
            pass
    pp = gcom.people(sc, m["gym_id"])
    return {i: gw._text(pp[i].get("full_name"), "Member") for i in ids if i in pp and i != m["id"]}


def render_class_feeds(sc, m, gym_name):
    import gympulse_community as gcom
    cls = my_classes(sc, m)
    if not cls:
        st.caption("Book or attend a class and its feed shows up here: share the group photo and tag classmates.")
        return
    pick = st.selectbox("Class", [str(c["id"]) for c in cls],
                        format_func=lambda i: next(f"{c.get('name') or 'Class'} · {c['_start']:%a %d %b, %I:%M %p}"
                                                   for c in cls if str(c["id"]) == i), key="eg_cls_pick")
    mates = classmates(sc, m, pick)
    if not m.get("community_blocked"):
        with st.expander("Post to this class", icon=":material/add_a_photo:"):
            composer(sc, m, gym_name, key=f"eg_cls_new_{pick}", class_id=pick, classmates=mates)
    try:
        posts = sc.table("community_posts").select("*").eq("gym_id", m["gym_id"]).eq("class_id", pick) \
            .eq("hidden", False).order("created_at", desc=True).limit(30).execute().data or []
    except Exception:
        posts = []
    if not posts:
        st.caption("No posts from this class yet. Be the first 📸")
    ids = {p["id"] for p in posts}
    for p in [x for x in gcom.load_feed(sc, m["gym_id"], 200) if x["id"] in ids]:
        gcom._post_card(sc, m, p, gym_name)


# ------------------------------------------------------------------ gym side
def render_owner_tabs(supabase, gym_id, gym_name, staff):
    """Challenges, polls & questions, and recognition for the gym's community panel."""
    if not ready(supabase):
        st.info("Challenges, polls and recognition need a one-time setup: run sql/phase24_community_engage.sql "
                "in the Supabase SQL Editor.")
        return
    t1, t2, t3 = st.tabs(["Challenges", "Polls & questions", "Recognition"])
    with t1:
        _owner_challenges(supabase, gym_id, gym_name)
    with t2:
        _owner_polls(supabase, gym_id, gym_name)
    with t3:
        _owner_recognition(supabase, gym_id, gym_name)


def _owner_challenges(sc, gym_id, gym_name):
    n = settle_challenges(sc, gym_id, None, gym_name)
    if n:
        st.success(f"{n} member{'s' if n != 1 else ''} just finished a challenge: shout-outs posted.")
    with st.form("eg_new_ch", clear_on_submit=True):
        st.markdown("**New challenge**")
        a, b = st.columns([3, 1])
        title = a.text_input("Name", placeholder=f"e.g. 12 visits in {gw.today_local():%B}")
        badge = b.selectbox("Badge", ["🏆", "🔥", "💪", "⭐", "🥇", "🏃", "🧘"])
        c, d, e = st.columns(3)
        goal = c.number_input("Visits to finish", 1, 100, 12)
        start = d.date_input("Starts", value=gw.today_local())
        end = e.date_input("Ends", value=gw.today_local() + timedelta(days=30))
        if st.form_submit_button("Start challenge", type="primary"):
            if not title.strip() or end < start:
                st.error("Give it a name, and an end date after the start.")
            else:
                sc.table("community_challenges").insert({"gym_id": gym_id, "title": title.strip()[:80],
                                                         "goal_visits": int(goal), "starts_on": start.isoformat(),
                                                         "ends_on": end.isoformat(), "badge": badge}).execute()
                sc.table("community_posts").insert({
                    "gym_id": gym_id, "member_id": None, "author_name": gym_name, "kind": "challenge", "pinned": False,
                    "body": f"{badge} New challenge: \"{title.strip()}\". {int(goal)} visits between {start:%d %b} and "
                            f"{end:%d %b}. Join from the top of the feed. Every check-in counts!"}).execute()
                st.session_state["cmo_flash"] = "Challenge started and announced to your members."
                st.rerun()
    chs = challenges(sc, gym_id, live_only=False)[:10]
    ents = entries(sc, gym_id, [c["id"] for c in chs])
    gw.table([{"Challenge": f"{c.get('badge') or ''} {c['title']}", "Goal": f"{c['goal_visits']} visits",
               "Dates": f"{pd.to_datetime(c['starts_on']):%d %b} – {pd.to_datetime(c['ends_on']):%d %b}",
               "Joined": sum(1 for e in ents if e["challenge_id"] == c["id"]),
               "Finished": sum(1 for e in ents if e["challenge_id"] == c["id"] and e.get("completed_at"))}
              for c in chs], empty="No challenges yet.")


def _owner_polls(sc, gym_id, gym_name):
    with st.form("eg_new_poll", clear_on_submit=True):
        st.markdown("**New poll**")
        q = st.text_input("Question", placeholder="e.g. Which new class should we add?")
        opts = [st.text_input(f"Option {i + 1}", key=f"eg_po_{i}") for i in range(4)]
        if st.form_submit_button("Post poll", type="primary"):
            options = [o.strip()[:60] for o in opts if o.strip()]
            if not q.strip() or len(options) < 2:
                st.error("Add a question and at least two options.")
            else:
                sc.table("community_posts").insert({"gym_id": gym_id, "member_id": None, "author_name": gym_name,
                                                    "kind": "poll", "body": q.strip()[:300],
                                                    "meta": {"options": options}}).execute()
                st.session_state["cmo_flash"] = "Poll posted."
                st.rerun()
    try:
        qs = sc.table("community_posts").select("*").eq("gym_id", gym_id).eq("kind", "question").eq("hidden", False) \
            .order("created_at", desc=True).limit(20).execute().data or []
        replied = {c["post_id"] for c in sc.table("community_comments").select("post_id, author_role")
                   .in_("post_id", [x["id"] for x in qs]).execute().data or [] if c.get("author_role") == "coach"} if qs else set()
    except Exception:
        qs, replied = [], set()
    st.markdown('<div class="section-label">ASK THE COACH</div>', unsafe_allow_html=True)
    if not qs:
        st.caption("No questions yet. Members ask from Create a post → Ask the coach.")
    for x in sorted(qs, key=lambda x: x["id"] in replied):
        with st.container(border=True):
            gw._md(f'<b>{gw._esc(x.get("author_name"))}</b> {"" if x["id"] in replied else "<span class=\'gp-pill gp-pill-amber\'>Needs an answer</span>"}'
                   f'<div class="cm-body">{gw._esc(x.get("body"))}</div>')
            coach_reply(sc, gym_id, x["id"], gym_name, key=f"q_{x['id']}")


def coach_reply(sc, gym_id, post_id, gym_name, key):
    with st.form(f"eg_cr_{key}", clear_on_submit=True, border=False):
        a, b = st.columns([5, 1.3], vertical_alignment="bottom")
        text = a.text_input("Reply as coach", label_visibility="collapsed", placeholder="Reply as coach…", max_chars=400)
        if b.form_submit_button("Reply", use_container_width=True) and text.strip():
            row = {"post_id": post_id, "gym_id": gym_id, "member_id": None, "author_name": gym_name,
                   "body": text.strip(), "author_role": "coach"}
            try:
                sc.table("community_comments").insert(row).execute()
            except Exception:
                row.pop("author_role")
                sc.table("community_comments").insert(row).execute()
            try:
                p = sc.table("community_posts").select("member_id").eq("id", post_id).limit(1).execute().data or []
                if p and p[0].get("member_id"):
                    _note(sc, gym_id, p[0]["member_id"], "comment", post_id)
            except Exception:
                pass
            st.session_state["cmo_flash"] = "Reply posted."
            st.rerun()


def _owner_recognition(sc, gym_id, gym_name):
    import gympulse_community as gcom
    pp = gcom.people(sc, gym_id)
    if not pp:
        st.caption("Members appear here once they've joined the community.")
        return
    week = f"{gw.today_local():%G-W%V}"
    with st.form("eg_motw", clear_on_submit=True):
        st.markdown("**⭐ Member of the week**")
        who = st.selectbox("Member", list(pp), format_func=lambda i: gw._text(pp[i].get("full_name"), "Member"))
        why = st.text_area("Why they're this week's star", max_chars=400,
                           placeholder="e.g. Never missed a 6am class this month and always helps newcomers.")
        ph = st.file_uploader("Photo (optional)", type=["jpg", "jpeg", "png", "webp", "heic", "heif"])
        if st.form_submit_button("Celebrate them", type="primary"):
            name = gw._text(pp[who].get("full_name"), "Member")
            pic = gcom._store_photo(sc, gym_id, frame_photo(gcom._image(ph.getvalue()), gym_name, "Member of the week"))\
                if ph is not None else None
            sc.table("community_posts").update({"pinned": False}).eq("gym_id", gym_id).execute()
            sc.table("community_posts").insert({"gym_id": gym_id, "member_id": None, "author_name": gym_name,
                                                "kind": "recognition", "pinned": True, "photo": pic,
                                                "body": f"⭐ Member of the week: {name}!" + (f"\n{why.strip()}" if why.strip() else ""),
                                                "meta": {"member_id": who, "week": week}}).execute()
            give_badge(sc, gym_id, who, f"motw:{week}", f"⭐ Member of the week ({gw.today_local():%d %b})")
            _note(sc, gym_id, who, "badge", f"motw:{week}")
            st.session_state["cmo_flash"] = f"{name} is member of the week: pinned to the top of the feed."
            st.rerun()
    st.caption("Milestones (10, 25, 50, 100+ visits), membership anniversaries and monthly recaps are offered to "
               "members automatically as shareable cards. Challenge finishers get a shout-out automatically.")


CSS = """<style>
.eg-nudge { border:1px solid rgba(183,243,74,.28); background: rgba(183,243,74,.07); border-radius:14px;
  padding:10px 14px; margin:0 0 8px; font-size:14px; color: var(--gp-text, #F4F7FB); }
.eg-now { display:flex; align-items:center; gap:10px; margin:2px 0 10px; font-size:14px; color: var(--gp-text, #F4F7FB); }
.eg-dot { width:9px; height:9px; border-radius:50%; background:#B7F34A; box-shadow:0 0 0 4px rgba(183,243,74,.18); }
.eg-faces { display:flex; margin-left:4px; } .eg-faces > span { margin-left:-8px; border:2px solid var(--gp-bg,#070B14); border-radius:50%; }
.eg-kind { display:inline-block; font-size:12px; font-weight:800; border-radius:999px; padding:3px 10px; margin:6px 0 2px;
  background: rgba(53,211,232,.14); color:#35D3E8; }
.eg-checkin, .eg-challenge { background: rgba(183,243,74,.14); color:#B7F34A; }
.eg-recognition, .eg-milestone { background: rgba(255,184,77,.16); color:#FFB84D; }
.eg-ch-t { font-weight:800; font-size:16px; color: var(--gp-text, #F4F7FB); }
.eg-chips { display:flex; flex-wrap:wrap; gap:6px; justify-content:center; margin:6px 0 10px; }
.eg-chips span { font-size:12.5px; font-weight:700; border-radius:999px; padding:4px 10px; background: rgba(255,255,255,.07);
  color: var(--gp-text, #F4F7FB); }
.eg-bar { position:relative; border-radius:12px; background: rgba(255,255,255,.06); margin:6px 0; padding:9px 12px;
  display:flex; justify-content:space-between; overflow:hidden; font-size:14px; color: var(--gp-text, #F4F7FB); }
.eg-bar i { position:absolute; left:0; top:0; bottom:0; background: rgba(53,211,232,.22); }
.eg-bar.me i { background: rgba(183,243,74,.3); } .eg-bar span, .eg-bar b { position:relative; }
.cm-coach { font-size:11px; font-weight:800; color:#0A0F1E; background:#B7F34A; border-radius:999px; padding:1px 7px; margin-left:4px; }
</style>"""
