"""GymPulse AI · Member community: a private feed for each gym, inside the member app.

Members (signed in to their member page) post text and photos, like and comment.
The gym posts announcements (and can pin them), and moderates: reported posts first,
hide posts and comments, stop a member posting. Members accept short community rules
before their first post, can delete their own posts and comments, and report others.

Everything is read and written on the server with the service key, always limited to
the signed-in member's own gym. Photos are resized and stored in the "community"
storage bucket (or kept small inside the post if storage isn't set up).
Database: sql/phase21_community.sql.
"""
import base64
import io
import uuid
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

BUCKET = "community"
MAX_BODY = 1000
MAX_COMMENT = 400
POSTS_PER_DAY = 10
PAGE = 15
RULES = ["Be kind and supportive: everyone is at a different stage.",
         "Only post photos of yourself, or of people who said yes.",
         "No selling, spam, hate or adult content.",
         "Health or injury questions: ask a coach, not the feed.",
         "The gym can remove posts and stop accounts that break these rules."]
SQL_HINT = ("The community needs a one-time setup: open Supabase, go to SQL Editor, paste in the file "
            "sql/phase21_community.sql and press Run.")


# ------------------------------------------------------------------ helpers
def _when(stamp):
    t = pd.to_datetime(stamp, errors="coerce", utc=True)
    if pd.isna(t):
        return ""
    mins = int((datetime.now(timezone.utc) - t.to_pydatetime()).total_seconds() // 60)
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{mins} min ago"
    if mins < 1440:
        return f"{mins // 60} h ago"
    if mins < 10080:
        return f"{mins // 1440} d ago"
    return t.tz_convert(gw.APP_TZ).strftime("%d %b")


def _image(raw):
    """Resize a photo for the feed: up to 1080 px wide, JPEG. Returns bytes."""
    from PIL import Image, ImageOps
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except Exception:
        pass
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    img.thumbnail((1080, 1350))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=78, optimize=True)
    return out.getvalue()


def _store_photo(sc, gym_id, data):
    """Public URL in the community bucket, or a small inline image if storage isn't available."""
    path = f"{gym_id}/{uuid.uuid4().hex}.jpg"
    try:
        store = sc.storage.from_(BUCKET)
        store.upload(path, data, {"content-type": "image/jpeg"})
        url = store.get_public_url(path)
        if isinstance(url, dict):
            url = url.get("publicURL") or url.get("publicUrl") or ""
        if url:
            return str(url).split("?")[0]
    except Exception:
        pass
    if len(data) > 350_000:                           # keep inline images small
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        img.thumbnail((720, 900))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=70, optimize=True)
        data = out.getvalue()
    return "data:image/jpeg;base64," + base64.b64encode(data).decode()


def enabled(sc, gym_id):
    try:
        g = sc.table("gyms").select("community_enabled").eq("id", gym_id).limit(1).execute().data or [{}]
        return g[0].get("community_enabled", True) is not False
    except Exception:
        return True


def ready(sc):
    try:
        sc.table("community_posts").select("id").limit(1).execute()
        return True
    except Exception:
        return False


def load_feed(sc, gym_id, limit=PAGE, include_hidden=False):
    """Posts (pinned first, newest first) with their likes, comments and authors' photos."""
    q = sc.table("community_posts").select("*").eq("gym_id", gym_id)
    if not include_hidden:
        q = q.eq("hidden", False)
    posts = q.order("pinned", desc=True).order("created_at", desc=True).limit(limit).execute().data or []
    if not posts:
        return []
    ids = [p["id"] for p in posts]
    likes = sc.table("community_likes").select("post_id, member_id").in_("post_id", ids).execute().data or []
    cq = sc.table("community_comments").select("*").in_("post_id", ids)
    if not include_hidden:
        cq = cq.eq("hidden", False)
    comments = cq.order("created_at").execute().data or []
    who = {p["member_id"] for p in posts if p.get("member_id")} | {c["member_id"] for c in comments if c.get("member_id")}
    photos = {}
    if who:
        try:
            photos = {m["id"]: m.get("photo") for m in sc.table("members").select("id, photo")
                      .in_("id", list(who)).execute().data or []}
        except Exception:
            pass
    for p in posts:
        p["likes"] = [x["member_id"] for x in likes if x["post_id"] == p["id"]]
        p["comments"] = [c for c in comments if c["post_id"] == p["id"]]
        p["avatar"] = photos.get(p.get("member_id"))
        for c in p["comments"]:
            c["avatar"] = photos.get(c.get("member_id"))
    return posts


def _author(p, gym_name):
    if p.get("member_id"):
        return gw._esc(p.get("author_name") or "Member"), ""
    return gw._esc(gym_name), ' <span class="gp-pill gp-pill-lime" style="font-size:11px">Gym</span>'


CSS = """<style>
.cm-name { font-weight:800; color: var(--gp-text, #F4F7FB); font-size:15px; }
.cm-when { font-size:12px; color: var(--gp-muted, #93A0B4); }
.cm-body { white-space:pre-wrap; font-size:15px; line-height:1.55; margin:8px 0 6px; color: var(--gp-text, #F4F7FB); }
.cm-img { width:100%; border-radius:16px; margin:6px 0; display:block; }
.cm-pin { font-size:12px; color:#B7F34A; font-weight:700; margin-bottom:4px; }
.cm-c { font-size:14px; line-height:1.45; margin:4px 0; }
.cm-c b { color: var(--gp-text, #F4F7FB); }
.cm-ring { width:62px; height:62px; border-radius:50%; padding:3px; margin:0 auto 2px;
  background: linear-gradient(135deg, #B7F34A, #35D3E8); }
.cm-ring.seen { background: rgba(147,160,180,.35); }
.cm-ring.add { background: rgba(147,160,180,.25); position:relative; }
.cm-ring > div { border:3px solid var(--gp-bg, #070B14); border-radius:50%; overflow:hidden; }
.cm-plus { position:absolute; right:-2px; bottom:-2px; width:22px; height:22px; border-radius:50%; background:#B7F34A;
  color:#0A0F1E; font-weight:900; display:flex; align-items:center; justify-content:center; font-size:16px;
  border:2px solid var(--gp-bg, #070B14); }
.cm-prof { text-align:center; padding:8px 0 4px; }
.cm-prof-name { font-size:22px; font-weight:800; color: var(--gp-text, #F4F7FB); margin-top:8px; }
.cm-prof-bio { color: var(--gp-muted, #93A0B4); font-size:14px; margin:4px auto 0; max-width:420px; white-space:pre-wrap; }
.cm-stat b { display:block; font-size:20px; font-weight:800; color: var(--gp-text, #F4F7FB); }
.cm-stat span { font-size:12px; color: var(--gp-muted, #93A0B4); }
.cm-tile { width:100%; aspect-ratio:1/1; object-fit:cover; border-radius:10px; display:block; }
.cm-tile-t { width:100%; aspect-ratio:1/1; border-radius:10px; padding:10px; overflow:hidden; font-size:12.5px;
  line-height:1.35; background: linear-gradient(135deg, rgba(183,243,74,.16), rgba(53,211,232,.16));
  color: var(--gp-text, #F4F7FB); }
.cm-bub { border-radius:18px; padding:9px 14px; margin:4px 0; max-width:78%; font-size:14.5px; line-height:1.45;
  white-space:pre-wrap; word-wrap:break-word; }
.cm-me { background: linear-gradient(135deg, #B7F34A, #35D3E8); color:#0A0F1E; margin-left:auto; border-bottom-right-radius:6px; }
.cm-them { background: var(--gp-s2, #172033); color: var(--gp-text, #F4F7FB); border-bottom-left-radius:6px; }
.cm-story { border-radius:18px; overflow:hidden; background:#000; }
.cm-story img { width:100%; max-height:70vh; object-fit:contain; display:block; }
.cm-story-t { padding:28px 18px; font-size:20px; font-weight:700; text-align:center; color:#0A0F1E;
  background: linear-gradient(135deg, #B7F34A, #35D3E8); min-height:240px; display:flex; align-items:center;
  justify-content:center; white-space:pre-wrap; }
.cm-bar { height:3px; border-radius:3px; background: rgba(255,255,255,.18); margin-bottom:10px; display:flex; gap:4px; }
.cm-bar i { flex:1; border-radius:3px; background: rgba(255,255,255,.25); }
.cm-bar i.on { background:#B7F34A; }
[class*="st-key-cm_act_"] [data-testid="stHorizontalBlock"], [class*="st-key-cm_crow_"] [data-testid="stHorizontalBlock"],
[class*="st-key-cm_hd_"] [data-testid="stHorizontalBlock"], [class*="st-key-cm_row_"] [data-testid="stHorizontalBlock"],
[class*="st-key-cm_pbtn"] [data-testid="stHorizontalBlock"], [class*="st-key-cm_stats"] [data-testid="stHorizontalBlock"],
[class*="st-key-cm_grid"] [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 8px !important; }
[class*="st-key-cm_act_"] [data-testid="stColumn"], [class*="st-key-cm_pbtn"] [data-testid="stColumn"],
[class*="st-key-cm_stats"] [data-testid="stColumn"], [class*="st-key-cm_grid"] [data-testid="stColumn"] {
  min-width: 0 !important; width: auto !important; flex: 1 1 0 !important; }
[class*="st-key-cm_crow_"] [data-testid="stColumn"], [class*="st-key-cm_hd_"] [data-testid="stColumn"],
[class*="st-key-cm_row_"] [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; flex: 1 1 auto !important; }
[class*="st-key-cm_crow_"] [data-testid="stColumn"]:last-child, [class*="st-key-cm_row_"] [data-testid="stColumn"]:last-child,
[class*="st-key-cm_hd_"] [data-testid="stColumn"]:first-child, [class*="st-key-cm_row_"] [data-testid="stColumn"]:first-child {
  flex: 0 0 auto !important; }
[class*="st-key-cm_act_"] button { padding: 4px 8px !important; min-height: 38px !important; }
[class*="st-key-cm_crow_"] button { padding: 0 10px !important; min-height: 30px !important; }
[class*="st-key-cm_hd_"] button, [class*="st-key-cm_row_"] .stButton:first-of-type button[kind="tertiary"] {
  padding: 0 !important; min-height: 0 !important; font-weight: 800 !important; font-size: 15px !important;
  justify-content: flex-start !important; }
[class*="st-key-cm_stories"] [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; overflow-x: auto !important;
  gap: 10px !important; padding-bottom: 4px; scrollbar-width: none; }
[class*="st-key-cm_stories"] [data-testid="stColumn"] { flex: 0 0 74px !important; min-width: 74px !important; width: 74px !important; }
[class*="st-key-cm_stories"] button { padding: 0 2px !important; min-height: 0 !important; font-size: 12px !important;
  width: 100%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
[class*="st-key-cm_stats"] button { flex-direction: column !important; min-height: 56px !important; line-height: 1.2 !important; }
[class*="st-key-cm_grid"] button { min-height: 0 !important; padding: 2px 4px !important; font-size: 12px !important; }
[class*="st-key-cm_hd_"] [data-testid="stVerticalBlock"], [class*="st-key-cm_row_"] [data-testid="stVerticalBlock"],
[class*="st-key-cm_stories"] [data-testid="stVerticalBlock"] { gap: 2px !important; }
[class*="st-key-cm_stories"] { margin-bottom: -10px; }
[class*="st-key-cm_hd_"] .cm-when, [class*="st-key-cm_row_"] .cm-when { margin-top: 0 !important; }
[class*="st-key-cm_chat"] { max-height: 55vh; overflow-y: auto; }
[class*="st-key-cm_topbar"] [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 6px !important; }
[class*="st-key-cm_topbar"] [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; flex: 1 1 auto !important; }
[class*="st-key-cm_topbar"] [data-testid="stColumn"]:last-child { flex: 0 0 auto !important; }
[class*="st-key-cm_topbar"] [data-testid="stPopover"] button { border: none !important; background: transparent !important;
  box-shadow: none !important; min-height: 44px !important; padding: 0 10px !important; font-size: 15px !important; }
[class*="st-key-cm_topbar"] [data-testid="stPopover"] button span[role="img"] { font-size: 26px !important; }
[class*="st-key-cm_topbar"] [data-testid="stPopover"] button > div > div[aria-hidden="true"] { display: none !important; }
[class*="st-key-cm_topbar"] [data-testid="stPopover"] button p { color: var(--gp-text, #F4F7FB) !important; font-weight: 800 !important; }
[class*="st-key-cm_nav_bar"] [data-testid="stButtonGroup"] > div { flex-wrap: nowrap !important; width: 100% !important; }
[class*="st-key-cm_nav_bar"] [data-testid="stButtonGroup"] { border: none !important; }
[class*="st-key-cm_nav_bar"] button { flex: 1 1 0 !important; min-width: 0 !important; padding: 6px 4px 9px !important;
  min-height: 44px !important; white-space: nowrap !important; border: none !important; border-radius: 0 !important;
  background: transparent !important; box-shadow: none !important; color: var(--gp-muted, #93A0B4) !important;
  border-bottom: 2px solid transparent !important; font-weight: 800 !important; }
[class*="st-key-cm_nav_bar"] button span[role="img"], [class*="st-key-cm_nav_bar"] button p { font-size: 26px !important; }
[class*="st-key-cm_topbar"] [data-testid="stPopover"] button p { font-size: 15px !important; }
[class*="st-key-cm_topbar"] [data-testid="stPopover"] button span[role="img"] { font-size: 26px !important; vertical-align: middle !important; }
[class*="st-key-cm_nav_bar"] button[aria-checked="true"], [class*="st-key-cm_nav_bar"] button[data-selected="true"] {
  color: #B7F34A !important; border-bottom-color: #B7F34A !important; }
[class*="st-key-cm_scope"] button { padding: 4px 14px !important; }
</style>"""


def _post_html(p, gym_name, header=True):
    name, badge = _author(p, gym_name)
    img = f'<img class="cm-img" src="{gw._esc(p["photo"])}" alt="">' if p.get("photo") else ""
    pin = '<div class="cm-pin">📌 Pinned by the gym</div>' if p.get("pinned") else ""
    head = ('<div style="display:flex;align-items:center;gap:10px">'
            + gw.avatar_html(p.get("author_name") or gym_name, p.get("avatar"), 40)
            + f'<div><div class="cm-name">{name}{badge}</div><div class="cm-when">{_when(p.get("created_at"))}</div>'
            + '</div></div>') if header else ""
    return (pin + head + (f'<div class="cm-body">{gw._esc(p.get("body"))}</div>' if p.get("body") else "") + img)


# ------------------------------------------------------------------ social data (phase 22)
def social_ready(sc):
    try:
        sc.table("community_follows").select("follower_id").limit(1).execute()
        return True
    except Exception:
        return False


def people(sc, gym_id):
    """{member_id: member} for everyone in the community (accepted the rules, not archived)."""
    def fetch():
        cols = "id, full_name, photo, community_agreed_at, community_bio, community_dm, community_blocked, archived"
        try:
            rows = gw.fetch_all(sc.table("members").select(cols + ", community_email_notify").eq("gym_id", gym_id)
                                .order("full_name"))
        except Exception:
            rows = None
        if rows is None:
            try:
                rows = gw.fetch_all(sc.table("members").select(cols).eq("gym_id", gym_id).order("full_name"))
            except Exception:
                rows = None
        if rows is None:
            rows = gw.fetch_all(sc.table("members").select("id, full_name, photo, community_agreed_at, archived")
                                .eq("gym_id", gym_id).order("full_name"))
        return {r["id"]: r for r in rows if r.get("community_agreed_at") and not r.get("archived")}
    return gw._cached(("cm_people", gym_id), fetch, ttl=20)


def _follows(sc, gym_id):
    def fetch():
        try:
            return sc.table("community_follows").select("follower_id, followee_id").eq("gym_id", gym_id) \
                .execute().data or []
        except Exception:
            return []
    return gw._cached(("cm_follows", gym_id), fetch, ttl=10)


def following_of(sc, gym_id, mid):
    return {f["followee_id"] for f in _follows(sc, gym_id) if f["follower_id"] == mid}


def followers_of(sc, gym_id, mid):
    return {f["follower_id"] for f in _follows(sc, gym_id) if f["followee_id"] == mid}


def _blocks(sc, gym_id, mid):
    """(people I blocked, people who blocked me)."""
    try:
        rows = sc.table("community_blocks").select("blocker_id, blocked_id").eq("gym_id", gym_id).execute().data or []
    except Exception:
        return set(), set()
    return ({r["blocked_id"] for r in rows if r["blocker_id"] == mid},
            {r["blocker_id"] for r in rows if r["blocked_id"] == mid})


def _bust(gym_id):
    cache = st.session_state.get("_cache") or {}
    for k in [k for k in cache if isinstance(k, tuple) and k[:1] in (("cm_follows",), ("cm_people",))]:
        cache.pop(k, None)


def toggle_follow(sc, m, other_id):
    if other_id in following_of(sc, m["gym_id"], m["id"]):
        sc.table("community_follows").delete().eq("follower_id", m["id"]).eq("followee_id", other_id).execute()
    else:
        try:
            sc.table("community_follows").insert({"gym_id": m["gym_id"], "follower_id": m["id"],
                                                  "followee_id": other_id}).execute()
            notify(sc, m, other_id, "follow")
        except Exception:
            pass
    _bust(m["gym_id"])


# ------------------------------------------------------------------ notifications (phase 23)
EMAIL_GAP_MIN = 30


def notify(sc, actor, member_id, kind):
    """Tell member_id that actor followed them / messaged them: in the app, and by email (at most every
    EMAIL_GAP_MIN minutes per kind, if they allow it). Never fails the action that caused it."""
    try:
        now = datetime.now(timezone.utc)
        if kind == "message":                       # one unread "messaged you" per person, kept fresh
            old = sc.table("community_notifications").select("id").eq("member_id", member_id) \
                .eq("actor_id", actor["id"]).eq("kind", "message").is_("read_at", "null").limit(1).execute().data
            if old:
                sc.table("community_notifications").update({"created_at": now.isoformat()}).eq("id", old[0]["id"]).execute()
                return
        if kind == "follow":                        # follow, unfollow, follow again: notify once a day
            since = (now - timedelta(days=1)).isoformat()
            if sc.table("community_notifications").select("id").eq("member_id", member_id).eq("actor_id", actor["id"]) \
                    .eq("kind", "follow").gte("created_at", since).limit(1).execute().data:
                return
        row = {"gym_id": actor["gym_id"], "member_id": member_id, "actor_id": actor["id"], "kind": kind,
               "created_at": now.isoformat()}
        res = sc.table("community_notifications").insert(row).execute().data or []
        _maybe_email(sc, actor, member_id, kind, (res[0] if res else {}).get("id"))
    except Exception:
        pass


def _maybe_email(sc, actor, member_id, kind, note_id):
    rows = sc.table("members").select("id, full_name, email, gym_id, community_email_notify") \
        .eq("id", member_id).limit(1).execute().data or []
    who = rows[0] if rows else None
    if not who or "@" not in gw._text(who.get("email")) or who.get("community_email_notify") is False:
        return
    since = (datetime.now(timezone.utc) - timedelta(minutes=EMAIL_GAP_MIN)).isoformat()
    recent = sc.table("community_notifications").select("id").eq("member_id", member_id).eq("kind", kind) \
        .gte("emailed_at", since).limit(1).execute().data
    if recent:
        return
    import gympulse_email as ge
    import gympulse_portal as gportal
    gym = gportal._gym(sc, who["gym_id"])[2]
    first, name = _first(who), gw._text(actor.get("full_name"), "A member")
    if kind == "message":
        subject = f"{name} sent you a message"
        line = f"<b>{ge.esc(name)}</b> sent you a message in the {ge.esc(gym)} community."
    else:
        subject = f"{name} started following you"
        line = f"<b>{ge.esc(name)}</b> started following you in the {ge.esc(gym)} community."
    url = gportal.login_url()
    body = (f"<p>Hi {ge.esc(first)},</p><p>{line}</p>" + ge.button("Open the community", url)
            + "<p style='color:#6B7686;font-size:13px'>Sign in with your email and the code we send you, then open "
              "Community. To stop these emails: Community → Me → Edit profile.</p>")
    text = (f"Hi {first},\n\n{subject} in the {gym} community.\nOpen it: {url}\n\n"
            "To stop these emails: Community → Me → Edit profile.")
    if gportal._email(gw._text(who["email"]).strip(), subject, ge.layout(subject, body, subject), text) and note_id:
        sc.table("community_notifications").update({"emailed_at": datetime.now(timezone.utc).isoformat()}) \
            .eq("id", note_id).execute()


def notifications(sc, m, limit=30):
    try:
        return sc.table("community_notifications").select("*").eq("member_id", m["id"]) \
            .order("created_at", desc=True).limit(limit).execute().data or []
    except Exception:
        return []


def unread_notes(sc, m):
    try:
        return len(sc.table("community_notifications").select("id").eq("member_id", m["id"])
                   .is_("read_at", "null").execute().data or [])
    except Exception:
        return 0


def _mark_read(sc, m, kind=None, actor_id=None):
    try:
        q = sc.table("community_notifications").update({"read_at": datetime.now(timezone.utc).isoformat()}) \
            .eq("member_id", m["id"]).is_("read_at", "null")
        if kind:
            q = q.eq("kind", kind)
        if actor_id:
            q = q.eq("actor_id", actor_id)
        q.execute()
    except Exception:
        pass


def _note_open(sc, m, n):
    st.session_state.pop("cm_notes_open", None)
    _mark_read(sc, m, n["kind"], n.get("actor_id"))
    st.session_state["cm_back"] = "feed"
    if n["kind"] == "message":
        _go("chat", cm_chat=n["actor_id"])
    elif n["kind"] in ("badge", "comment", "challenge") or not n.get("actor_id"):
        _go("me" if n["kind"] == "badge" else "feed")
    else:
        _go("profile", cm_pid=n["actor_id"])


def notes_list(sc, m):
    """Notifications inside the bell's drop-down (doesn't cover the app)."""
    st.markdown("**Notifications**")
    rows = notifications(sc, m)
    pp = people(sc, m["gym_id"])
    if not rows:
        st.caption("Nothing yet. When someone follows you or sends you a message, you'll see it here.")
    for n in rows:
        a = pp.get(n.get("actor_id")) or {"full_name": "A member"}
        what = {"message": "sent you a message", "follow": "started following you",
                "tag": "tagged you in a class post"}.get(n["kind"])
        if n["kind"] == "badge":
            a, what = {"full_name": gw._text(m.get("full_name"))}, ""
        label = (f"{gw._text(a.get('full_name'), 'A member')} {what}" if what else
                 "🏅 You earned a new badge: see it on your profile" if n["kind"] == "badge" else
                 "💬 The coach replied to your post" if n["kind"] == "comment" else "🏆 Challenge update")
        x, y = st.container(key=f"cm_row_note_{n['id']}").columns([1, 6], vertical_alignment="center")
        gw._md(gw.avatar_html(a.get("full_name"), a.get("photo"), 40), x)
        with y:
            if st.button(label, key=f"cm_note_{n['id']}", type="tertiary"):
                _note_open(sc, m, n)
                st.rerun()
            gw._md(f'<div class="cm-when">{"🟢 " if not n.get("read_at") else ""}{_when(n.get("created_at"))}</div>')
    if rows and st.button("Mark all as read", key="cm_notes_all", use_container_width=True):
        _mark_read(sc, m)
        st.rerun()


def can_message(sc, m, other):
    """(ok, reason) for m sending a direct message to other."""
    if m.get("community_blocked"):
        return False, "The gym has paused messaging from your account."
    mine, theirs = _blocks(sc, m["gym_id"], m["id"])
    if other["id"] in mine:
        return False, "You've blocked this member."
    if other["id"] in theirs:
        return False, "You can't message this member."
    pref = other.get("community_dm") or "everyone"
    if pref == "nobody":
        return False, f"{_first(other)} isn't taking messages."
    if pref == "following" and m["id"] not in following_of(sc, m["gym_id"], other["id"]):
        return False, f"{_first(other)} only takes messages from people they follow."
    return True, ""


def _first(p):
    return (gw._text(p.get("full_name")).split() or ["Member"])[0]


def unread_count(sc, m):
    try:
        return len(sc.table("community_dms").select("id").eq("recipient_id", m["id"]).is_("read_at", "null")
                   .execute().data or [])
    except Exception:
        return 0


# ------------------------------------------------------------------ member side (inside the member page)
def _go(view, **kw):
    st.session_state["cm_view"] = view
    for k, v in kw.items():
        st.session_state[k] = v


def _open_profile(pid):
    st.session_state["cm_back"] = st.session_state.get("cm_view", "feed")
    _go("profile", cm_pid=pid)


def _open_chat(pid):
    st.session_state["cm_back"] = st.session_state.get("cm_view", "feed")
    _go("chat", cm_chat=pid)


def active_only(profile):
    """The gym's choice: only members with a running plan can use the community (default yes)."""
    return dict(((profile or {}).get("settings") or {}).get("community") or {}).get("active_only", True) is not False


def member_active(m, today=None):
    """(active, end date): a plan that runs today or later, and not suspended or archived."""
    today = today or gw.today_local()
    end = pd.to_datetime(m.get("membership_end"), errors="coerce")
    end = None if pd.isna(end) else end.date()
    ok = bool(end and end >= today and not m.get("suspended") and not m.get("archived"))
    return ok, end


def render_member(sc, m, gym_name, profile=None):
    st.markdown(CSS, unsafe_allow_html=True)
    if not ready(sc):
        st.info(f"The {gym_name} community is coming soon.")
        return
    if not enabled(sc, m["gym_id"]):
        st.info(f"{gym_name} hasn't switched the community on.")
        return
    if active_only(profile):
        ok, end = member_active(m)
        if not ok:
            with st.container(border=True):
                st.markdown(f"#### The {gw._esc(gym_name)} community is for active members")
                if m.get("suspended"):
                    st.markdown("Your membership is paused. When it's active again, you'll be straight back in.")
                elif end:
                    st.markdown(f"Your membership ended on **{end:%d %B %Y}**. Renew and you'll be straight back in, "
                                "with your posts, followers and messages just as you left them.")
                else:
                    st.markdown("Once the gym has added your plan, you'll get access. Ask at the front desk.")
                pay = dict(((profile or {}).get("settings") or {}).get("collect") or {})
                if pay.get("paystack_link") and not m.get("suspended"):
                    st.link_button("Renew with Paystack", pay["paystack_link"], type="primary",
                                   use_container_width=True)
                st.caption("Your renewal details are on the Home tab.")
            return
    flash = st.session_state.pop("cm_flash", None)
    if flash:
        st.toast(flash)
    if not m.get("community_agreed_at"):
        with st.container(border=True):
            st.markdown(f"#### Welcome to the {gw._esc(gym_name)} community")
            st.markdown("Share your progress, post stories, follow and message other members, and see what's "
                        "happening at the gym. Only members of your gym can see it.")
            st.markdown("\n".join(f"- {r}" for r in RULES))
            if st.button("I agree, let me in", type="primary", key="cm_agree", use_container_width=True):
                sc.table("members").update({"community_agreed_at": datetime.now(timezone.utc).isoformat()}) \
                    .eq("id", m["id"]).execute()
                _bust(m["gym_id"])
                st.rerun()
        return
    social = social_ready(sc)
    view = st.session_state.get("cm_view", "feed")
    if not social and view not in ("feed",):
        view = "feed"
    if view in ("feed", "search", "inbox", "me") and social:
        unread = unread_count(sc, m)
        labels = {"feed": ":material/home:", "search": ":material/search:",
                  "inbox": f":material/send:{f' {unread}' if unread else ''}",
                  "me": ":material/person:"}
        st.session_state["cm_nav_bar"] = view           # the menu always shows the current screen

        def _nav():
            st.session_state["cm_view"] = st.session_state.get("cm_nav_bar") or view
        nav, bell = st.container(key="cm_topbar").columns([5, 1], vertical_alignment="center")
        with nav:
            st.segmented_control("Community", list(labels), format_func=labels.get, key="cm_nav_bar",
                                 on_change=_nav, label_visibility="collapsed", width="stretch")
        with bell:
            n = unread_notes(sc, m)
            with st.popover(f":material/notifications:{f' {n}' if n else ''}", use_container_width=True):
                notes_list(sc, m)
    if view == "search":
        _search(sc, m, gym_name)
    elif view == "inbox":
        _inbox(sc, m, gym_name)
    elif view == "chat":
        _chat(sc, m, st.session_state.get("cm_chat"), gym_name)
    elif view in ("profile", "me"):
        _profile(sc, m, m["id"] if view == "me" else st.session_state.get("cm_pid"), gym_name)
    else:
        _feed(sc, m, gym_name, social)


def _back():
    if st.button("Back", icon=":material/arrow_back:", key="cm_back_btn", type="tertiary"):
        st.session_state["cm_view"] = st.session_state.get("cm_back", "feed")
        if st.session_state["cm_view"] in ("profile", "chat"):
            st.session_state["cm_view"] = "feed"
        st.rerun()


# ---------------- feed
def _feed(sc, m, gym_name, social):
    if social:
        _stories_bar(sc, m, gym_name)
    import gympulse_engage as ge
    st.markdown(ge.CSS, unsafe_allow_html=True)
    ge.render_top(sc, m, gym_name, None)
    if m.get("community_blocked"):
        st.warning(f"{gym_name} has paused posting from your account. You can still read the community.")
    else:
        with st.expander("Create a post", icon=":material/add_photo_alternate:",
                         expanded=bool(st.session_state.get("cm_compose_open"))):
            if ge.ready(sc):
                ge.composer(sc, m, gym_name)
            else:
                _composer(sc, m)
    scope = "all"
    if social:
        opts = {"all": "Everyone", "following": "Following"}
        if ge.ready(sc):
            opts["classes"] = "Classes"
        scope = st.segmented_control("Show", list(opts), default="all", key="cm_scope",
                                     format_func=opts.get, label_visibility="collapsed") or "all"
    if scope == "classes":
        ge.render_class_feeds(sc, m, gym_name)
        return
    limit = st.session_state.get("cm_limit", PAGE)
    posts = load_feed(sc, m["gym_id"], limit)
    if social:
        mine, theirs = _blocks(sc, m["gym_id"], m["id"])
        posts = [p for p in posts if p.get("member_id") not in mine | theirs]
        if scope == "following":
            fol = following_of(sc, m["gym_id"], m["id"]) | {m["id"]}
            posts = [p for p in posts if p.get("member_id") in fol or not p.get("member_id")]
    if not posts:
        st.caption("No posts yet. Be the first to say hello 👋" if scope == "all" else
                   "Follow members to see their posts here. Try Search.")
    for p in posts:
        _post_card(sc, m, p, gym_name, social)
    if len(posts) >= limit:
        if st.button("Show more", key="cm_more", use_container_width=True):
            st.session_state["cm_limit"] = limit + PAGE
            st.rerun()


def _composer(sc, m, key="cm_new"):
    with st.form(key, clear_on_submit=True, border=False):
        body = st.text_area("Share something with your gym", max_chars=MAX_BODY, label_visibility="collapsed",
                            placeholder="New personal best? A class you loved? Say hi 👋")
        photo = st.file_uploader("Photo (optional)", type=["jpg", "jpeg", "png", "webp", "heic", "heif"])
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
    if len(today) >= POSTS_PER_DAY:
        st.error("That's a lot of posts today. Please try again tomorrow.")
        return
    pic = None
    if photo is not None:
        try:
            pic = _store_photo(sc, m["gym_id"], _image(photo.getvalue()))
        except Exception:
            st.error("That photo couldn't be read. Try a JPG or PNG.")
            return
    sc.table("community_posts").insert({"gym_id": m["gym_id"], "member_id": m["id"],
                                        "author_name": gw._text(m.get("full_name"), "Member"),
                                        "body": body.strip()[:MAX_BODY], "photo": pic}).execute()
    st.session_state["cm_flash"] = "Posted."
    st.rerun()


def _post_card(sc, m, p, gym_name, social=True):
    mine = p.get("member_id") == m["id"]
    liked = m["id"] in p["likes"]
    with st.container(border=True, key=f"cm_post_{p['id']}"):
        if p.get("pinned"):
            gw._md('<div class="cm-pin">📌 Pinned by the gym</div>')
        a, b = st.container(key=f"cm_hd_{p['id']}").columns([1, 8], vertical_alignment="center")
        gw._md(gw.avatar_html(p.get("author_name") or gym_name, p.get("avatar"), 40), a)
        with b:
            if p.get("member_id") and social:
                st.button(gw._text(p.get("author_name"), "Member"), key=f"cm_au_{p['id']}", type="tertiary",
                          on_click=_open_profile, args=(p["member_id"],))
            else:
                gw._md(f'<div class="cm-name">{_author(p, gym_name)[0]}{_author(p, gym_name)[1]}</div>')
            gw._md(f'<div class="cm-when" style="margin-top:-6px">{_when(p.get("created_at"))}</div>')
        import gympulse_engage as ge
        ge.post_label(sc, m, p)
        gw._md(_post_html(p, gym_name, header=False).replace('<div class="cm-pin">📌 Pinned by the gym</div>', ""))
        ge.post_poll(sc, m, p)
        x, y, z = st.container(key=f"cm_act_{p['id']}").columns([1.2, 1.4, 1.4])
        if x.button(f"{'❤️' if liked else '🤍'} {len(p['likes']) or ''}".strip(), key=f"cm_like_{p['id']}",
                    use_container_width=True):
            if liked:
                sc.table("community_likes").delete().eq("post_id", p["id"]).eq("member_id", m["id"]).execute()
            else:
                try:
                    sc.table("community_likes").insert({"post_id": p["id"], "gym_id": m["gym_id"],
                                                        "member_id": m["id"]}).execute()
                except Exception:
                    pass
            st.rerun()
        show_key = f"cm_show_{p['id']}"
        n = len(p["comments"])
        if y.button(f"💬 {n}" if n else "💬 Comment", key=f"cm_cbtn_{p['id']}", use_container_width=True):
            st.session_state[show_key] = not st.session_state.get(show_key, False)
            st.rerun()
        if mine:
            if z.button("Delete", key=f"cm_del_{p['id']}", use_container_width=True):
                sc.table("community_posts").delete().eq("id", p["id"]).eq("member_id", m["id"]).execute()
                st.session_state["cm_flash"] = "Post deleted."
                st.rerun()
        elif z.button("Report", key=f"cm_rep_{p['id']}", use_container_width=True):
            sc.table("community_reports").insert({"gym_id": m["gym_id"], "post_id": p["id"], "member_id": m["id"],
                                                  "reason": "Reported from the member app"}).execute()
            st.session_state["cm_flash"] = "Thanks. The gym will take a look."
            st.rerun()
        if st.session_state.get(show_key):
            for cm in p["comments"]:
                name = gw._esc(cm.get("author_name") or ("Member" if cm.get("member_id") else gym_name))
                c1, c2 = st.container(key=f"cm_crow_{cm['id']}").columns([6, 1], vertical_alignment="center")
                badge = ('<span class="cm-coach">Coach</span>' if cm.get("author_role") == "coach"
                         else " (gym)" if not cm.get("member_id") else "")
                gw._md(f'<div class="cm-c"><b>{name}</b>{badge} '
                       f'{gw._esc(cm.get("body"))} <span class="cm-when">· {_when(cm.get("created_at"))}</span></div>', c1)
                if cm.get("member_id") == m["id"] and c2.button("✕", key=f"cm_cdel_{cm['id']}", help="Delete"):
                    sc.table("community_comments").delete().eq("id", cm["id"]).eq("member_id", m["id"]).execute()
                    st.rerun()
            if not m.get("community_blocked"):
                with st.form(f"cm_cf_{p['id']}", clear_on_submit=True, border=False):
                    text = st.text_input("Write a comment", max_chars=MAX_COMMENT, label_visibility="collapsed",
                                         placeholder="Write a comment…")
                    if st.form_submit_button("Send") and text.strip():
                        sc.table("community_comments").insert({
                            "post_id": p["id"], "gym_id": m["gym_id"], "member_id": m["id"],
                            "author_name": gw._text(m.get("full_name"), "Member"),
                            "body": text.strip()[:MAX_COMMENT]}).execute()
                        st.rerun()


# ---------------- stories
def active_stories(sc, gym_id):
    now = datetime.now(timezone.utc).isoformat()
    try:
        rows = sc.table("community_stories").select("*").eq("gym_id", gym_id).eq("hidden", False) \
            .gt("expires_at", now).order("created_at").execute().data or []
    except Exception:
        return []
    return rows


def _seen(sc, m, ids):
    if not ids:
        return set()
    try:
        return {r["story_id"] for r in sc.table("community_story_views").select("story_id")
                .eq("member_id", m["id"]).in_("story_id", list(ids)).execute().data or []}
    except Exception:
        return set()


def _stories_bar(sc, m, gym_name):
    stories = active_stories(sc, m["gym_id"])
    mine_b, theirs_b = _blocks(sc, m["gym_id"], m["id"])
    stories = [s for s in stories if s.get("member_id") not in mine_b | theirs_b]
    groups = {}
    for s in stories:
        groups.setdefault(s.get("member_id") or "gym", []).append(s)
    seen = _seen(sc, m, [s["id"] for s in stories])
    pp = people(sc, m["gym_id"])
    fol = following_of(sc, m["gym_id"], m["id"])
    order = ["gym"] if "gym" in groups else []
    order += sorted([k for k in groups if k not in ("gym", m["id"])],
                    key=lambda k: (all(s["id"] in seen for s in groups[k]), k not in fol))
    cols = st.container(key="cm_stories").columns(len(order) + 1)
    with cols[0]:
        mine = groups.get(m["id"])
        ring = "cm-ring" if mine else "cm-ring add"
        gw._md(f'<div class="{ring}"><div>{gw.avatar_html(m.get("full_name"), m.get("photo"), 50)}</div>'
               + ("" if mine else '<span class="cm-plus">+</span>') + "</div>")
        if st.button("Your story", key="cm_story_me", type="tertiary"):
            if mine:
                st.session_state["cm_story_pos"] = [0, 0]
                story_dialog(sc, m, [m["id"]], groups, gym_name)
            else:
                add_story_dialog(sc, m)
    for i, k in enumerate(order, start=1):
        with cols[i]:
            who = pp.get(k, {}) if k != "gym" else {"full_name": gym_name}
            done = all(s["id"] in seen for s in groups[k])
            gw._md(f'<div class="cm-ring{" seen" if done else ""}"><div>'
                   f'{gw.avatar_html(who.get("full_name") or "Member", who.get("photo"), 50)}</div></div>')
            label = gym_name if k == "gym" else _first(who)
            if st.button(label, key=f"cm_story_{k}", type="tertiary"):
                st.session_state["cm_story_pos"] = [0, 0]
                story_dialog(sc, m, order[i - 1:], groups, gym_name)
    if mine := groups.get(m["id"]):
        if st.button("＋ Add to your story", key="cm_story_add", type="tertiary"):
            add_story_dialog(sc, m)


def _story_times():
    now = datetime.now(timezone.utc)
    return {"created_at": now.isoformat(), "expires_at": (now + timedelta(hours=24)).isoformat()}


@st.dialog("New story")
def add_story_dialog(sc, m):
    st.caption("Stories disappear after 24 hours. Only you can see them later, in your story archive.")
    with st.form("cm_story_new", border=False):
        photo = st.file_uploader("Photo", type=["jpg", "jpeg", "png", "webp", "heic", "heif"])
        text = st.text_input("Text (optional)", max_chars=140)
        import gympulse_engage as ge
        c1, c2 = st.columns(2)
        stk = c1.selectbox("Sticker", ge.STICKERS, format_func=lambda s: s or "No sticker")
        frm = c2.toggle("Gym frame", value=True)
        go = st.form_submit_button("Share story", type="primary", use_container_width=True)
    if go:
        if photo is None and not text.strip():
            st.error("Add a photo or some text.")
            return
        pic = None
        if photo is not None:
            raw = _image(photo.getvalue())
            if stk or frm:
                import gympulse_portal as gportal
                raw = ge.frame_photo(raw, gportal._gym(sc, m["gym_id"])[2], stk, frm)
            pic = _store_photo(sc, m["gym_id"], raw)
        sc.table("community_stories").insert({"gym_id": m["gym_id"], "member_id": m["id"],
                                              "author_name": gw._text(m.get("full_name"), "Member"),
                                              "photo": pic, "body": text.strip(), **_story_times()}).execute()
        st.session_state["cm_flash"] = "Story shared for 24 hours."
        st.rerun()


@st.dialog("Stories", width="small")
def story_dialog(sc, m, order, groups, gym_name):
    pos = st.session_state.get("cm_story_pos") or [0, 0]
    if pos[0] >= len(order):
        st.session_state.pop("cm_story_pos", None)
        st.rerun()
    k = order[pos[0]]
    items = groups[k]
    s = items[min(pos[1], len(items) - 1)]
    who = gym_name if k == "gym" else gw._text(s.get("author_name"), "Member")
    try:
        sc.table("community_story_views").insert({"story_id": s["id"], "gym_id": m["gym_id"],
                                                  "member_id": m["id"]}).execute()
    except Exception:
        pass
    bars = "".join(f'<i class="{"on" if j <= pos[1] else ""}"></i>' for j in range(len(items)))
    gw._md(f'<div class="cm-bar">{bars}</div><div class="cm-name">{gw._esc(who)} '
           f'<span class="cm-when">· {_when(s.get("created_at"))}</span></div>')
    if s.get("photo"):
        gw._md(f'<div class="cm-story"><img src="{gw._esc(s["photo"])}" alt=""></div>'
               + (f'<div class="cm-body" style="text-align:center">{gw._esc(s.get("body"))}</div>' if s.get("body") else ""))
    else:
        gw._md(f'<div class="cm-story"><div class="cm-story-t">{gw._esc(s.get("body"))}</div></div>')
    a, b = st.columns(2)
    if a.button("Previous", use_container_width=True, disabled=pos == [0, 0], key="cm_st_prev"):
        st.session_state["cm_story_pos"] = ([pos[0], pos[1] - 1] if pos[1] > 0 else
                                            [pos[0] - 1, len(groups[order[pos[0] - 1]]) - 1])
        st.rerun(scope="fragment")
    last = pos[0] == len(order) - 1 and pos[1] >= len(items) - 1
    if b.button("Close" if last else "Next", type="primary", use_container_width=True, key="cm_st_next"):
        if last:
            st.session_state.pop("cm_story_pos", None)
            st.rerun()
        st.session_state["cm_story_pos"] = [pos[0], pos[1] + 1] if pos[1] < len(items) - 1 else [pos[0] + 1, 0]
        st.rerun(scope="fragment")
    if s.get("member_id") == m["id"]:
        if st.button("Delete this story", key="cm_st_del", type="tertiary"):
            sc.table("community_stories").delete().eq("id", s["id"]).eq("member_id", m["id"]).execute()
            st.session_state.pop("cm_story_pos", None)
            st.rerun()
    elif s.get("member_id") and st.button(f"View {_first({'full_name': who})}'s profile", key="cm_st_prof",
                                         type="tertiary"):
        st.session_state.pop("cm_story_pos", None)
        _open_profile(s["member_id"])
        st.rerun()


# ---------------- profile
def _profile(sc, m, pid, gym_name):
    pp = people(sc, m["gym_id"])
    me = pid == m["id"]
    if not me:
        _back()
    p = pp.get(pid) or ({**m} if me else None)
    if not p:
        st.info("This member isn't in the community.")
        return
    mine_b, theirs_b = _blocks(sc, m["gym_id"], m["id"])
    if pid in theirs_b:
        st.info("This profile isn't available.")
        return
    try:
        posts = sc.table("community_posts").select("*").eq("gym_id", m["gym_id"]).eq("member_id", pid) \
            .eq("hidden", False).order("created_at", desc=True).limit(60).execute().data or []
    except Exception:
        posts = []
    fol, fing = followers_of(sc, m["gym_id"], pid), following_of(sc, m["gym_id"], pid)
    gw._md('<div class="cm-prof">' + '<div style="display:flex;justify-content:center">'
           + gw.avatar_html(p.get("full_name"), p.get("photo"), 92) + "</div>"
           + f'<div class="cm-prof-name">{gw._esc(p.get("full_name"))}</div>'
           + (f'<div class="cm-prof-bio">{gw._esc(p.get("community_bio"))}</div>' if p.get("community_bio") else "")
           + "</div>")
    a, b, c = st.container(key="cm_stats").columns(3)
    a.button(f"**{len(posts)}** {'post' if len(posts) == 1 else 'posts'}", key="cm_st_posts", type="tertiary",
             use_container_width=True)
    if b.button(f"**{len(fol)}** {'follower' if len(fol) == 1 else 'followers'}", key="cm_st_fol", type="tertiary",
                use_container_width=True):
        people_dialog(sc, m, "Followers", fol)
    if c.button(f"**{len(fing)}** following", key="cm_st_fing", type="tertiary", use_container_width=True):
        people_dialog(sc, m, "Following", fing)
    import gympulse_engage as ge
    st.markdown(ge.CSS, unsafe_allow_html=True)
    ge.profile_extras(sc, m, pid)
    if me:
        x, y = st.container(key="cm_pbtn_me").columns(2)
        if x.button("Edit profile", key="cm_edit", icon=":material/edit:", use_container_width=True):
            edit_profile_dialog(sc, m)
        if y.button("Story archive", key="cm_arch", icon=":material/history:", use_container_width=True):
            archive_dialog(sc, m)
    else:
        following = pid in following_of(sc, m["gym_id"], m["id"])
        x, y, z = st.container(key="cm_pbtn_other").columns([1.3, 1.3, 1])
        if x.button("Following" if following else "Follow", key="cm_follow", use_container_width=True,
                    type="secondary" if following else "primary"):
            toggle_follow(sc, m, pid)
            st.rerun()
        if y.button("Message", key="cm_msg", icon=":material/chat:", use_container_width=True):
            _open_chat(pid)
            st.rerun()
        if z.button("Unblock" if pid in mine_b else "Block", key="cm_block", use_container_width=True):
            if pid in mine_b:
                sc.table("community_blocks").delete().eq("blocker_id", m["id"]).eq("blocked_id", pid).execute()
                st.session_state["cm_flash"] = "Unblocked."
            else:
                sc.table("community_blocks").insert({"gym_id": m["gym_id"], "blocker_id": m["id"],
                                                     "blocked_id": pid}).execute()
                sc.table("community_follows").delete().eq("follower_id", m["id"]).eq("followee_id", pid).execute()
                sc.table("community_follows").delete().eq("follower_id", pid).eq("followee_id", m["id"]).execute()
                _bust(m["gym_id"])
                st.session_state["cm_flash"] = "Blocked. They can't message you or see your profile."
            st.rerun()
        if pid in mine_b:
            st.caption("You've blocked this member.")
            return
    if not posts:
        st.caption("No posts yet." if not me else "You haven't posted yet. Share something from the Feed.")
        return
    st.markdown('<div class="section-label">POSTS</div>', unsafe_allow_html=True)
    for i in range(0, len(posts), 3):
        cols = st.container(key=f"cm_grid_{i}").columns(3)
        for col, post in zip(cols, posts[i:i + 3]):
            with col:
                if post.get("photo"):
                    gw._md(f'<img class="cm-tile" src="{gw._esc(post["photo"])}" alt="">')
                else:
                    gw._md(f'<div class="cm-tile-t">{gw._esc(gw._text(post.get("body"))[:140])}</div>')
                if st.button("Open", key=f"cm_open_{post['id']}", type="tertiary", use_container_width=True):
                    post_dialog(sc, m, post["id"], gym_name)


@st.dialog("Post")
def post_dialog(sc, m, post_id, gym_name):
    feed = [p for p in load_feed(sc, m["gym_id"], 200) if p["id"] == post_id]
    if not feed:
        st.info("This post is no longer available.")
        return
    _post_card(sc, m, feed[0], gym_name)


@st.dialog("People")
def people_dialog(sc, m, title, ids):
    st.markdown(f"**{title}**")
    pp = people(sc, m["gym_id"])
    rows = [pp[i] for i in ids if i in pp]
    if not rows:
        st.caption("Nobody yet.")
    for p in rows:
        _person_row(sc, m, p, f"dlg_{title}")


@st.dialog("Edit profile")
def edit_profile_dialog(sc, m):
    pp = people(sc, m["gym_id"]).get(m["id"], m)
    opts = {"everyone": "Everyone in my gym", "following": "Only people I follow", "nobody": "Nobody"}
    with st.form("cm_prof_form", border=False):
        bio = st.text_area("Bio", value=gw._text(pp.get("community_bio")), max_chars=160,
                           placeholder="e.g. Morning lifter · training for my first 10k")
        dm = st.radio("Who can message me", list(opts), format_func=opts.get,
                      index=list(opts).index(pp.get("community_dm") or "everyone"))
        mail = st.toggle("Email me when someone messages or follows me",
                         value=pp.get("community_email_notify", m.get("community_email_notify", True)) is not False)
        st.caption("Your name and photo come from your gym details (My details tab).")
        if st.form_submit_button("Save", type="primary", use_container_width=True):
            upd = {"community_bio": bio.strip() or None, "community_dm": dm, "community_email_notify": bool(mail)}
            try:
                sc.table("members").update(upd).eq("id", m["id"]).execute()
            except Exception:                        # phase 23 not run yet
                upd.pop("community_email_notify")
                sc.table("members").update(upd).eq("id", m["id"]).execute()
            _bust(m["gym_id"])
            st.session_state["cm_flash"] = "Profile saved."
            st.rerun()


@st.dialog("Story archive")
def archive_dialog(sc, m):
    st.caption("Your stories after their 24 hours. Only you can see these.")
    now = datetime.now(timezone.utc).isoformat()
    try:
        rows = sc.table("community_stories").select("*").eq("member_id", m["id"]).lte("expires_at", now) \
            .order("created_at", desc=True).limit(60).execute().data or []
    except Exception:
        rows = []
    if not rows:
        st.caption("Nothing here yet.")
    for i in range(0, len(rows), 3):
        cols = st.columns(3)
        for col, s in zip(cols, rows[i:i + 3]):
            with col:
                if s.get("photo"):
                    gw._md(f'<img class="cm-tile" src="{gw._esc(s["photo"])}" alt="">')
                else:
                    gw._md(f'<div class="cm-tile-t">{gw._esc(s.get("body"))}</div>')
                st.caption(pd.to_datetime(s["created_at"]).strftime("%d %b"))


# ---------------- search
def _person_row(sc, m, p, key):
    a, b, c = st.container(key=f"cm_row_{key}_{p['id']}").columns([1, 5, 2.2], vertical_alignment="center")
    gw._md(gw.avatar_html(p.get("full_name"), p.get("photo"), 40), a)
    with b:
        st.button(gw._text(p.get("full_name"), "Member"), key=f"cm_pr_{key}_{p['id']}", type="tertiary",
                  on_click=_open_profile, args=(p["id"],))
        if p.get("community_bio"):
            gw._md(f'<div class="cm-when" style="margin-top:-6px">{gw._esc(gw._text(p["community_bio"])[:60])}</div>')
    if p["id"] != m["id"]:
        f = p["id"] in following_of(sc, m["gym_id"], m["id"])
        if c.button("Following" if f else "Follow", key=f"cm_pf_{key}_{p['id']}", use_container_width=True,
                    type="secondary" if f else "primary"):
            toggle_follow(sc, m, p["id"])
            st.rerun()


def _search(sc, m, gym_name):
    import gympulse_engage as ge
    if ge.ready(sc):
        tab = st.segmented_control("Find", ["people", "buddies"], default="people", key="cm_find",
                                   format_func={"people": "People", "buddies": "🤝 Find a buddy"}.get,
                                   label_visibility="collapsed") or "people"
        if tab == "buddies":
            ge.render_buddies(sc, m, gym_name)
            return
    q = st.text_input("Search members", placeholder="Search members by name", key="cm_q",
                      label_visibility="collapsed", icon=":material/search:")
    pp = people(sc, m["gym_id"])
    mine_b, theirs_b = _blocks(sc, m["gym_id"], m["id"])
    others = [p for p in pp.values() if p["id"] != m["id"] and p["id"] not in theirs_b]
    if q.strip():
        n = q.strip().lower()
        rows = [p for p in others if n in gw._text(p.get("full_name")).lower()]
        if not rows:
            st.caption("No members found.")
    else:
        fol = following_of(sc, m["gym_id"], m["id"])
        counts = {}
        for f in _follows(sc, m["gym_id"]):
            counts[f["followee_id"]] = counts.get(f["followee_id"], 0) + 1
        rows = sorted([p for p in others if p["id"] not in fol], key=lambda p: -counts.get(p["id"], 0))[:15]
        st.markdown('<div class="section-label">MEMBERS TO FOLLOW</div>', unsafe_allow_html=True)
        if not rows:
            st.caption(f"You follow everyone in the {gym_name} community 🎉")
    for p in rows[:40]:
        _person_row(sc, m, p, "s")


# ---------------- messages
def _threads(sc, m):
    try:
        rows = sc.table("community_dms").select("*").eq("gym_id", m["gym_id"]) \
            .or_(f"sender_id.eq.{m['id']},recipient_id.eq.{m['id']}").order("created_at", desc=True) \
            .limit(500).execute().data or []
    except Exception:
        try:
            a = sc.table("community_dms").select("*").eq("sender_id", m["id"]).execute().data or []
            b = sc.table("community_dms").select("*").eq("recipient_id", m["id"]).execute().data or []
            rows = sorted(a + b, key=lambda r: str(r.get("created_at")), reverse=True)
        except Exception:
            rows = []
    out = {}
    for r in rows:
        other = r["recipient_id"] if r["sender_id"] == m["id"] else r["sender_id"]
        t = out.setdefault(other, {"last": r, "unread": 0})
        if r["recipient_id"] == m["id"] and not r.get("read_at"):
            t["unread"] += 1
    return out


def _inbox(sc, m, gym_name):
    threads = _threads(sc, m)
    pp = people(sc, m["gym_id"])
    if not threads:
        st.caption("No messages yet. Open a member's profile and tap Message, or find people in Search.")
        return
    for other, t in threads.items():
        p = pp.get(other)
        if not p:
            continue
        r = t["last"]
        a, b, c = st.container(key=f"cm_row_in_{other}").columns([1, 5, 1.2], vertical_alignment="center")
        gw._md(gw.avatar_html(p.get("full_name"), p.get("photo"), 44), a)
        with b:
            st.button(gw._text(p.get("full_name"), "Member"), key=f"cm_th_{other}", type="tertiary",
                      on_click=_open_chat, args=(other,))
            prefix = "You: " if r["sender_id"] == m["id"] else ""
            gw._md(f'<div class="cm-when" style="margin-top:-6px;{"font-weight:700;color:#F4F7FB" if t["unread"] else ""}">'
                   f'{gw._esc(prefix + gw._text(r.get("body"))[:60])} · {_when(r.get("created_at"))}</div>')
        if t["unread"]:
            gw._md(f'<span class="gp-pill gp-pill-lime">{t["unread"]}</span>', c)


def _chat(sc, m, other_id, gym_name):
    _back()
    pp = people(sc, m["gym_id"])
    other = pp.get(other_id)
    if not other:
        st.info("This member isn't in the community.")
        return
    a, b = st.container(key="cm_hd_chat").columns([1, 8], vertical_alignment="center")
    gw._md(gw.avatar_html(other.get("full_name"), other.get("photo"), 40), a)
    b.button(gw._text(other.get("full_name"), "Member"), key="cm_chat_prof", type="tertiary",
             on_click=_open_profile, args=(other_id,))
    try:
        rows = sc.table("community_dms").select("*").eq("gym_id", m["gym_id"]) \
            .in_("sender_id", [m["id"], other_id]).in_("recipient_id", [m["id"], other_id]) \
            .order("created_at").limit(300).execute().data or []
    except Exception:
        rows = []
    rows = [r for r in rows if {r["sender_id"], r["recipient_id"]} == {m["id"], other_id}]
    unread = [r["id"] for r in rows if r["recipient_id"] == m["id"] and not r.get("read_at")]
    _mark_read(sc, m, "message", other_id)
    if unread:
        try:
            sc.table("community_dms").update({"read_at": datetime.now(timezone.utc).isoformat()}) \
                .in_("id", unread).execute()
        except Exception:
            pass
    with st.container(key="cm_chat"):
        if not rows:
            st.caption(f"Say hi to {_first(other)} 👋")
        for r in rows:
            me = r["sender_id"] == m["id"]
            gw._md(f'<div class="cm-bub {"cm-me" if me else "cm-them"}">{gw._esc(r.get("body"))}</div>'
                   f'<div class="cm-when" style="text-align:{"right" if me else "left"};margin:-2px 4px 4px">'
                   f'{_when(r.get("created_at"))}</div>')
    ok, why = can_message(sc, m, other)
    if not ok:
        st.caption(why)
        return
    with st.form("cm_dm", clear_on_submit=True, border=False):
        x, y = st.columns([5, 1.3], vertical_alignment="bottom")
        text = x.text_input("Message", max_chars=1000, label_visibility="collapsed", placeholder="Message…")
        send = y.form_submit_button("Send", type="primary", use_container_width=True)
    if send and text.strip():
        since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        try:
            recent = sc.table("community_dms").select("id").eq("sender_id", m["id"]).gte("created_at", since) \
                .execute().data or []
        except Exception:
            recent = []
        if len(recent) >= 60:
            st.error("You're sending a lot of messages. Please wait a little.")
            return
        sc.table("community_dms").insert({"gym_id": m["gym_id"], "sender_id": m["id"], "recipient_id": other_id,
                                          "body": text.strip()[:1000]}).execute()
        notify(sc, m, other_id, "message")
        st.rerun()


# ------------------------------------------------------------------ gym side (owner and staff)
def render_owner(supabase, gym_id):
    gw.intro("Member community", ":material/forum:",
             "A private feed for your members inside their member app: progress photos, shout-outs and your "
             "announcements. Only your members can see it. You can pin, hide and remove posts.")
    st.markdown(CSS, unsafe_allow_html=True)
    if not ready(supabase):
        st.info(SQL_HINT)
        return
    flash = st.session_state.pop("cmo_flash", None)
    if flash:
        st.success(flash)
    staff = st.session_state.get("role") == "staff"
    gym_name = gw._text((st.session_state.get("user_profile") or {}).get("business_name"), "Your gym")
    on = enabled(supabase, gym_id)
    if not staff:
        if st.toggle("Community switched on for my members", value=on, key="cmo_on") != on:
            supabase.table("gyms").update({"community_enabled": not on}).eq("id", gym_id).execute()
            st.rerun()
        prof = st.session_state.get("user_profile") or {}
        ao = active_only(prof)
        new_ao = st.toggle("Only members with an active plan can use it", value=ao, key="cmo_active",
                           help="Members whose plan has ended see a renew button instead. They're back in, with "
                                "everything as they left it, as soon as they renew.")
        if new_ao != ao:
            import gympulse_grow as gg
            cur = dict((prof.get("settings") or {}).get("community") or {})
            gg._save_settings(supabase, prof.get("id") or st.session_state.get("auth_user", {}).get("id"),
                              {"community": {**cur, "active_only": bool(new_ao)}}, "Community setting saved.")
            st.rerun()

    with st.form("cmo_new", clear_on_submit=True):
        body = st.text_area(f"Post as {gym_name}", max_chars=MAX_BODY,
                            placeholder="New class times, a challenge, member of the month…")
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        photo = c1.file_uploader("Photo (optional)", type=["jpg", "jpeg", "png", "webp", "heic", "heif"])
        pin = c2.checkbox("Pin to the top")
        go = st.form_submit_button("Post", type="primary")
    if go and (body.strip() or photo is not None):
        pic = _store_photo(supabase, gym_id, _image(photo.getvalue())) if photo is not None else None
        if pin:
            supabase.table("community_posts").update({"pinned": False}).eq("gym_id", gym_id).execute()
        supabase.table("community_posts").insert({"gym_id": gym_id, "member_id": None, "author_name": gym_name,
                                                  "body": body.strip()[:MAX_BODY], "photo": pic,
                                                  "pinned": bool(pin)}).execute()
        st.session_state["cmo_flash"] = "Posted to your members."
        st.rerun()

    if social_ready(supabase):
        with st.expander("Stories (24 hours)", icon=":material/amp_stories:"):
            with st.form("cmo_story", clear_on_submit=True, border=False):
                sp = st.file_uploader("Story photo", type=["jpg", "jpeg", "png", "webp", "heic", "heif"], key="cmo_sp")
                stx = st.text_input("Story text (optional)", max_chars=140)
                if st.form_submit_button("Share a gym story", type="primary") and (sp is not None or stx.strip()):
                    pic = _store_photo(supabase, gym_id, _image(sp.getvalue())) if sp is not None else None
                    supabase.table("community_stories").insert({"gym_id": gym_id, "member_id": None,
                                                                "author_name": gym_name, "photo": pic,
                                                                "body": stx.strip(), **_story_times()}).execute()
                    st.session_state["cmo_flash"] = "Story shared with your members for 24 hours."
                    st.rerun()
            live = active_stories(supabase, gym_id)
            if not live:
                st.caption("No stories right now.")
            for sto in live:
                a, b = st.columns([5, 1], vertical_alignment="center")
                a.markdown(f"**{gw._esc(sto.get('author_name'))}** · {gw._esc(gw._text(sto.get('body'))[:60]) or 'photo'}"
                           f" · {_when(sto.get('created_at'))}")
                if b.button("Remove", key=f"cmo_srm_{sto['id']}"):
                    supabase.table("community_stories").update({"hidden": True}).eq("id", sto["id"]) \
                        .eq("gym_id", gym_id).execute()
                    st.rerun()

    import gympulse_engage as ge
    _eng_ready = ge.ready(supabase)
    st.markdown('<div class="section-label">CHALLENGES · POLLS · RECOGNITION</div>', unsafe_allow_html=True)
    ge.render_owner_tabs(supabase, gym_id, gym_name, staff)
    st.markdown('<div class="section-label">POSTS</div>', unsafe_allow_html=True)
    try:
        reports = supabase.table("community_reports").select("*").eq("gym_id", gym_id).eq("resolved", False) \
            .order("created_at", desc=True).execute().data or []
    except Exception:
        reports = []
    reported = {r["post_id"] for r in reports if r.get("post_id")}
    posts = load_feed(supabase, gym_id, st.session_state.get("cmo_limit", 20), include_hidden=True)
    posts.sort(key=lambda p: (p["id"] not in reported,))
    if reported:
        st.warning(f"{len(reported)} post{'s' if len(reported) != 1 else ''} reported by members: shown first.")
    if not posts:
        st.caption("No posts yet. Post a welcome message to get things started.")
    for p in posts:
        with st.container(border=True, key=f"cmo_post_{p['id']}"):
            if p["id"] in reported:
                gw._md('<span class="gp-pill gp-pill-amber">Reported</span>')
            if p.get("hidden"):
                gw._md('<span class="gp-pill">Hidden from members</span>')
            gw._md(_post_html(p, gym_name))
            st.caption(f"❤️ {len(p['likes'])} · 💬 {len(p['comments'])}")
            if not p.get("hidden") and _eng_ready:
                import gympulse_engage as ge
                ge.coach_reply(supabase, gym_id, p["id"], gym_name, key=f"p_{p['id']}")
            for cm in p["comments"]:
                x, y = st.columns([6, 1.2], vertical_alignment="center")
                gw._md(f'<div class="cm-c" style="{"opacity:.45" if cm.get("hidden") else ""}"><b>'
                       f'{gw._esc(cm.get("author_name") or gym_name)}</b> {gw._esc(cm.get("body"))}</div>', x)
                if y.button("Show" if cm.get("hidden") else "Hide", key=f"cmo_ch_{cm['id']}"):
                    supabase.table("community_comments").update({"hidden": not cm.get("hidden")}) \
                        .eq("id", cm["id"]).eq("gym_id", gym_id).execute()
                    st.rerun()
            b = st.columns(4)
            if b[0].button("Unpin" if p.get("pinned") else "Pin", key=f"cmo_pin_{p['id']}", use_container_width=True):
                if not p.get("pinned"):
                    supabase.table("community_posts").update({"pinned": False}).eq("gym_id", gym_id).execute()
                supabase.table("community_posts").update({"pinned": not p.get("pinned")}).eq("id", p["id"]).execute()
                st.rerun()
            if b[1].button("Show" if p.get("hidden") else "Hide", key=f"cmo_hide_{p['id']}", use_container_width=True):
                supabase.table("community_posts").update({"hidden": not p.get("hidden")}).eq("id", p["id"]).execute()
                _resolve(supabase, gym_id, p["id"])
                st.rerun()
            if p["id"] in reported and b[2].button("Looks fine", key=f"cmo_ok_{p['id']}", use_container_width=True):
                _resolve(supabase, gym_id, p["id"])
                st.rerun()
            if p.get("member_id") and not staff:
                blocked = _is_blocked(supabase, p["member_id"])
                if b[3].button("Allow posting" if blocked else "Stop posting", key=f"cmo_blk_{p['id']}",
                               use_container_width=True,
                               help="Stops this member posting and commenting. They can still read."):
                    supabase.table("members").update({"community_blocked": not blocked}) \
                        .eq("id", p["member_id"]).eq("gym_id", gym_id).execute()
                    st.session_state["cmo_flash"] = ("They can post again." if blocked else
                                                     "They can no longer post or comment.")
                    st.rerun()
    if len(posts) >= st.session_state.get("cmo_limit", 20):
        if st.button("Show more", key="cmo_more"):
            st.session_state["cmo_limit"] = st.session_state.get("cmo_limit", 20) + 20
            st.rerun()


def _resolve(supabase, gym_id, post_id):
    try:
        supabase.table("community_reports").update({"resolved": True}).eq("gym_id", gym_id).eq("post_id", post_id) \
            .execute()
    except Exception:
        pass


def _is_blocked(supabase, member_id):
    try:
        r = supabase.table("members").select("community_blocked").eq("id", member_id).limit(1).execute().data or [{}]
        return bool(r[0].get("community_blocked"))
    except Exception:
        return False
