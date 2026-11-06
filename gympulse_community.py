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
.cm-head { display:flex; align-items:center; gap:10px; }
.cm-name { font-weight:800; color: var(--gp-text, #F4F7FB); font-size:15px; }
.cm-when { font-size:12px; color: var(--gp-muted, #93A0B4); }
.cm-body { white-space:pre-wrap; font-size:15px; line-height:1.5; margin:10px 0 6px; color: var(--gp-text, #F4F7FB); }
.cm-img { width:100%; border-radius:14px; margin:6px 0; display:block; }
.cm-pin { font-size:12px; color:#B7F34A; font-weight:700; margin-bottom:4px; }
.cm-c { font-size:14px; line-height:1.45; margin:6px 0; }
.cm-c b { color: var(--gp-text, #F4F7FB); }
[class*="st-key-cm_act_"] [data-testid="stHorizontalBlock"],
[class*="st-key-cm_crow_"] [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 8px !important; }
[class*="st-key-cm_act_"] [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; flex: 1 1 0 !important; }
[class*="st-key-cm_crow_"] [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; flex: 1 1 auto !important; }
[class*="st-key-cm_crow_"] [data-testid="stColumn"]:last-child { flex: 0 0 auto !important; }
[class*="st-key-cm_act_"] button { padding: 4px 8px !important; min-height: 38px !important; }
[class*="st-key-cm_crow_"] button { padding: 0 10px !important; min-height: 30px !important; }
</style>"""


def _post_html(p, gym_name):
    name, badge = _author(p, gym_name)
    img = f'<img class="cm-img" src="{gw._esc(p["photo"])}" alt="">' if p.get("photo") else ""
    pin = '<div class="cm-pin">📌 Pinned by the gym</div>' if p.get("pinned") else ""
    return (pin + '<div class="cm-head">' + gw.avatar_html(p.get("author_name") or gym_name, p.get("avatar"), 40)
            + f'<div><div class="cm-name">{name}{badge}</div><div class="cm-when">{_when(p.get("created_at"))}</div>'
            + '</div></div>'
            + (f'<div class="cm-body">{gw._esc(p.get("body"))}</div>' if p.get("body") else "") + img)


# ------------------------------------------------------------------ member side (inside the member page)
def render_member(sc, m, gym_name):
    st.markdown(CSS, unsafe_allow_html=True)
    if not ready(sc):
        st.info(f"The {gym_name} community is coming soon.")
        return
    if not enabled(sc, m["gym_id"]):
        st.info(f"{gym_name} hasn't switched the community on.")
        return
    flash = st.session_state.pop("cm_flash", None)
    if flash:
        st.success(flash)
    if not m.get("community_agreed_at"):
        with st.container(border=True):
            st.markdown(f"#### Welcome to the {gw._esc(gym_name)} community")
            st.markdown("Share your progress, cheer each other on and see what's happening at the gym. "
                        "Only members of your gym can see it.")
            st.markdown("\n".join(f"- {r}" for r in RULES))
            if st.button("I agree, let me in", type="primary", key="cm_agree", use_container_width=True):
                sc.table("members").update({"community_agreed_at": datetime.now(timezone.utc).isoformat()}) \
                    .eq("id", m["id"]).execute()
                st.rerun()
        return
    if m.get("community_blocked"):
        st.warning(f"{gym_name} has paused posting from your account. You can still read the community.")
    else:
        _composer(sc, m)
    limit = st.session_state.get("cm_limit", PAGE)
    posts = load_feed(sc, m["gym_id"], limit)
    if not posts:
        st.caption("No posts yet. Be the first to say hello 👋")
    for p in posts:
        _post_card(sc, m, p, gym_name)
    if len(posts) >= limit:
        if st.button("Show more", key="cm_more", use_container_width=True):
            st.session_state["cm_limit"] = limit + PAGE
            st.rerun()


def _composer(sc, m):
    with st.form("cm_new", clear_on_submit=True):
        body = st.text_area("Share something with your gym", max_chars=MAX_BODY,
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


def _post_card(sc, m, p, gym_name):
    mine = p.get("member_id") == m["id"]
    liked = m["id"] in p["likes"]
    with st.container(border=True, key=f"cm_post_{p['id']}"):
        gw._md(_post_html(p, gym_name))
        a, b, c = st.container(key=f"cm_act_{p['id']}").columns([1.2, 1.4, 1.4])
        if a.button(f"{'❤️' if liked else '🤍'} {len(p['likes']) or ''}".strip(), key=f"cm_like_{p['id']}",
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
        if b.button(f"💬 {n}" if n else "💬 Comment", key=f"cm_cbtn_{p['id']}", use_container_width=True):
            st.session_state[show_key] = not st.session_state.get(show_key, False)
            st.rerun()
        if mine:
            if c.button("Delete", key=f"cm_del_{p['id']}", use_container_width=True):
                sc.table("community_posts").delete().eq("id", p["id"]).eq("member_id", m["id"]).execute()
                st.session_state["cm_flash"] = "Post deleted."
                st.rerun()
        elif c.button("Report", key=f"cm_rep_{p['id']}", use_container_width=True):
            sc.table("community_reports").insert({"gym_id": m["gym_id"], "post_id": p["id"], "member_id": m["id"],
                                                  "reason": "Reported from the member app"}).execute()
            st.session_state["cm_flash"] = "Thanks. The gym will take a look."
            st.rerun()
        if st.session_state.get(show_key):
            for cm in p["comments"]:
                name = gw._esc(cm.get("author_name") or ("Member" if cm.get("member_id") else gym_name))
                x, y = st.container(key=f"cm_crow_{cm['id']}").columns([6, 1], vertical_alignment="center")
                gw._md(f'<div class="cm-c"><b>{name}</b>{" (gym)" if not cm.get("member_id") else ""} '
                       f'{gw._esc(cm.get("body"))} <span class="cm-when">· {_when(cm.get("created_at"))}</span></div>', x)
                if cm.get("member_id") == m["id"] and y.button("✕", key=f"cm_cdel_{cm['id']}", help="Delete"):
                    sc.table("community_comments").delete().eq("id", cm["id"]).eq("member_id", m["id"]).execute()
                    st.rerun()
            if not m.get("community_blocked"):
                with st.form(f"cm_cf_{p['id']}", clear_on_submit=True):
                    text = st.text_input("Write a comment", max_chars=MAX_COMMENT, label_visibility="collapsed",
                                         placeholder="Write a comment…")
                    if st.form_submit_button("Send") and text.strip():
                        sc.table("community_comments").insert({
                            "post_id": p["id"], "gym_id": m["gym_id"], "member_id": m["id"],
                            "author_name": gw._text(m.get("full_name"), "Member"),
                            "body": text.strip()[:MAX_COMMENT]}).execute()
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
