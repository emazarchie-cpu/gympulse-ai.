"""GymPulse AI · Community member profile (one in-app screen, components v2).

Cover photo, profile photo (gradient ring when they have a live story), name and @handle, counts
(posts · followers · following · likes), Follow / Message / ⋯ (or Edit profile / Archive for
yourself), bio and chips (streak, goal, badges), story highlights, and icon tabs over an
edge-to-edge 3-column grid: Posts (pinned first), Reels and Tagged. Taps come back to Python as
events (open a post, followers, follow, message…). Database: sql/phase26_community_profiles.sql.
"""
import re

import streamlit as st

import gympulse_workspaces as gw

_CSS = r"""
:host { all: initial; }
* { box-sizing: border-box; font-family: Inter, -apple-system, system-ui, sans-serif; -webkit-tap-highlight-color: transparent; }
.pf { color:#F4F7FB; background:#070B14; border-radius:26px; overflow:hidden; border:1px solid rgba(255,255,255,.06); }
.cover { height:150px; background: radial-gradient(120% 140% at 0% 0%, rgba(183,243,74,.55), transparent 55%),
         radial-gradient(120% 140% at 100% 100%, rgba(53,211,232,.55), transparent 55%), #0E1626; background-size:cover;
         background-position:center; position:relative; }
.cover::after { content:''; position:absolute; inset:0; background:linear-gradient(transparent 45%, rgba(7,11,20,.85)); }
.top { position:relative; padding:0 18px; margin-top:-46px; display:flex; align-items:flex-end; gap:14px; z-index:1; }
.ring { width:98px; height:98px; border-radius:50%; padding:3px; background:#070B14; flex:0 0 auto; cursor:pointer; position:relative; }
.ring.live { background: linear-gradient(135deg,#B7F34A,#35D3E8); }
.ring .in { width:100%; height:100%; border-radius:50%; border:3px solid #070B14; overflow:hidden; display:flex; align-items:center;
            justify-content:center; background: linear-gradient(135deg,#B7F34A,#35D3E8); color:#0A0F1E; font-weight:900; font-size:30px; }
.ring img { width:100%; height:100%; object-fit:cover; }
.plus { position:absolute; right:2px; bottom:2px; width:26px; height:26px; border-radius:50%; background:#B7F34A; color:#0A0F1E;
        font-weight:900; display:flex; align-items:center; justify-content:center; border:3px solid #070B14; font-size:16px; }
.stats { display:flex; flex:1; justify-content:space-between; padding-bottom:6px; }
.st { text-align:center; cursor:pointer; min-width:0; } .st b { display:block; font-size:18px; font-weight:900; }
.st span { font-size:12px; color:#93A0B4; }
.who { padding:12px 18px 0; } .nm { font-size:22px; font-weight:900; letter-spacing:-.3px; }
.hd { color:#93A0B4; font-size:14px; margin-top:2px; }
.bio { font-size:14.5px; line-height:1.5; margin-top:8px; white-space:pre-wrap; }
.chips { display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; }
.chip { font-size:12.5px; font-weight:700; border-radius:999px; padding:5px 11px; background:rgba(255,255,255,.07); }
.chip.hot { background: linear-gradient(135deg, rgba(183,243,74,.25), rgba(53,211,232,.2)); }
.acts { display:flex; gap:8px; padding:14px 18px 4px; }
.b { flex:1; border:none; border-radius:14px; padding:11px 10px; font-size:14.5px; font-weight:800; cursor:pointer;
     background:rgba(255,255,255,.08); color:#F4F7FB; }
.b.pri { background: linear-gradient(135deg,#B7F34A,#35D3E8); color:#0A0F1E; }
.b.sq { flex:0 0 46px; font-size:18px; }
.hl { display:flex; gap:14px; overflow-x:auto; padding:14px 18px 6px; scrollbar-width:none; }
.hl::-webkit-scrollbar { display:none; }
.h { flex:0 0 auto; width:68px; text-align:center; cursor:pointer; }
.h .c { width:64px; height:64px; border-radius:50%; padding:2px; border:2px solid rgba(255,255,255,.25); margin:0 auto; }
.h .c > div { width:100%; height:100%; border-radius:50%; overflow:hidden; background:#18223a; display:flex; align-items:center;
              justify-content:center; font-size:24px; }
.h img { width:100%; height:100%; object-fit:cover; } .h span { display:block; font-size:12px; margin-top:6px; color:#C9D2E0;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.tabs { display:flex; border-bottom:1px solid rgba(255,255,255,.08); margin-top:8px; }
.tab { flex:1; text-align:center; padding:12px 0 10px; font-size:22px; color:#93A0B4; cursor:pointer; border-bottom:2px solid transparent; }
.tab.on { color:#F4F7FB; border-bottom-color:#B7F34A; }
.grid { display:grid; grid-template-columns:repeat(3,1fr); gap:2px; }
.t { position:relative; aspect-ratio:3/4; background:#111a2b; cursor:pointer; overflow:hidden; }
.t img { width:100%; height:100%; object-fit:cover; display:block; }
.t .tx { padding:10px; font-size:12.5px; line-height:1.35; height:100%; background:linear-gradient(135deg, rgba(183,243,74,.22), rgba(53,211,232,.18)); }
.t .ic { position:absolute; top:7px; right:7px; font-size:15px; text-shadow:0 1px 6px rgba(0,0,0,.6); }
.t .lk { position:absolute; left:7px; bottom:6px; font-size:12.5px; font-weight:800; text-shadow:0 1px 6px rgba(0,0,0,.7); }
.empty { padding:40px 18px; text-align:center; color:#93A0B4; font-weight:600; }
.lock { padding:30px 18px; text-align:center; color:#93A0B4; }
"""

_JS = r"""
export default function(component){
  const { data, parentElement, setTriggerValue } = component;
  const D = data || {}; const P = D.profile || {};
  let root = parentElement.querySelector('.pf');
  if (!root) { root = document.createElement('div'); root.className = 'pf'; parentElement.appendChild(root); }
  const esc = t => String(t ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const fire = (k, v) => setTriggerValue(k, {v: v ?? '', n: Date.now()});
  const n = x => x >= 1e6 ? (x/1e6).toFixed(1).replace('.0','')+'M' : x >= 1e4 ? (x/1e3).toFixed(1).replace('.0','')+'K' : String(x);
  let tab = root.dataset.tab || 'posts';
  function grid(){
    const list = tab === 'reels' ? (D.posts||[]).filter(p => p.video) : tab === 'tagged' ? (D.tagged||[]) : (D.posts||[]);
    if (!list.length) return `<div class="empty">${tab==='reels'?'No reels yet.':tab==='tagged'?'No tagged posts yet.':(P.me?'Share your first post from the Feed 📸':'No posts yet.')}</div>`;
    return `<div class="grid">${list.map(p => `<div class="t" data-id="${esc(p.id)}">
      ${p.img ? `<img src="${esc(p.img)}" loading="lazy" alt="">` : `<div class="tx">${esc(p.text)}</div>`}
      ${p.pinned ? '<span class="ic">📌</span>' : p.video ? '<span class="ic">▶︎</span>' : ''}
      ${p.likes ? `<span class="lk">♥ ${n(p.likes)}</span>` : ''}</div>`).join('')}</div>`;
  }
  function paint(){
    const S = P.stats || {};
    root.innerHTML = `
      <div class="cover" style="${P.cover ? `background-image:url('${esc(P.cover)}')` : ''}"></div>
      <div class="top">
        <div class="ring ${P.live ? 'live' : ''}" id="av"><div class="in">${P.avatar ? `<img src="${esc(P.avatar)}">` : esc(P.initials)}</div>
          ${P.me && !P.live ? '<span class="plus">+</span>' : ''}</div>
        <div class="stats">
          <div class="st"><b>${n(S.posts||0)}</b><span>posts</span></div>
          <div class="st" id="fol"><b>${n(S.followers||0)}</b><span>followers</span></div>
          <div class="st" id="fing"><b>${n(S.following||0)}</b><span>following</span></div>
          <div class="st"><b>${n(S.likes||0)}</b><span>likes</span></div>
        </div>
      </div>
      <div class="who"><div class="nm">${esc(P.name)}</div><div class="hd">@${esc(P.handle)}</div>
        ${P.bio ? `<div class="bio">${esc(P.bio)}</div>` : ''}
        <div class="chips">${(P.chips||[]).map((c,i) => `<span class="chip ${i===0&&P.hot?'hot':''}">${esc(c)}</span>`).join('')}</div></div>
      <div class="acts">${P.me ?
        `<button class="b" id="edit">Edit profile</button><button class="b" id="arch">Story archive</button><button class="b sq" id="newst">＋</button>` :
        P.blocked ? `<button class="b" id="block">Unblock</button>` :
        `<button class="b ${P.following?'':'pri'}" id="follow">${P.following?'Following':'Follow'}</button>
         <button class="b" id="msg">Message</button><button class="b sq" id="more">⋯</button>`}</div>
      ${P.blocked ? '<div class="lock">You blocked this member.</div>' : `
      ${(D.highlights||[]).length || P.me ? `<div class="hl">${P.me ? '<div class="h" id="hlnew"><div class="c"><div>＋</div></div><span>New</span></div>' : ''}
        ${(D.highlights||[]).map(h => `<div class="h" data-h="${esc(h.name)}"><div class="c"><div>${h.cover ? `<img src="${esc(h.cover)}">` : '✨'}</div></div>
        <span>${esc(h.name)}</span></div>`).join('')}</div>` : ''}
      <div class="tabs"><div class="tab ${tab==='posts'?'on':''}" data-t="posts">▦</div><div class="tab ${tab==='reels'?'on':''}" data-t="reels">▶︎</div>
        <div class="tab ${tab==='tagged'?'on':''}" data-t="tagged">◎</div></div>
      ${grid()}`}`;
    const on = (id, k, v) => { const el = root.querySelector('#'+id); if (el) el.onclick = () => fire(k, v); };
    on('fol','followers'); on('fing','following'); on('edit','edit'); on('arch','archive'); on('newst','newstory');
    on('follow','follow'); on('msg','message'); on('more','more'); on('block','block'); on('hlnew','archive');
    root.querySelector('#av').onclick = () => fire(P.live ? 'story' : (P.me ? 'newstory' : 'none'));
    root.querySelectorAll('.h[data-h]').forEach(el => el.onclick = () => fire('highlight', el.dataset.h));
    root.querySelectorAll('.tab').forEach(el => el.onclick = () => { tab = el.dataset.t; root.dataset.tab = tab; paint(); });
    root.querySelectorAll('.t[data-id]').forEach(el => el.onclick = () => fire('post', el.dataset.id));
  }
  paint();
}
"""

_comp = None
EVENTS = ("followers", "following", "edit", "archive", "newstory", "follow", "message", "more", "block", "story",
          "highlight", "post")


def _component():
    global _comp
    if _comp is None:
        _comp = st.components.v2.component("gp_profile", css=_CSS, js=_JS)
    return _comp


def handle_of(name):
    s = re.sub(r"[^a-z0-9]+", ".", gw._text(name).lower()).strip(".")
    return s or "member"


def profile_view(data, key):
    """Show the profile. Returns (event, value) once after a tap, or None."""
    holder = f"{key}_evt"

    def mk(name):
        def cb():
            v = st.session_state.get(key)
            val = getattr(v, name, None) if v is not None else None
            if val is None and isinstance(v, dict):
                val = v.get(name)
            if val:
                st.session_state[holder] = (name, val.get("v"))
        return cb

    _component()(key=key, data=data, **{f"on_{e}_change": mk(e) for e in EVENTS})
    return st.session_state.pop(holder, None)


# ------------------------------------------------------------------ Python side
def render(sc, m, pid, gym_name):
    import gympulse_community as gcom
    import gympulse_engage as ge
    pp = gcom.people(sc, m["gym_id"])
    me = pid == m["id"]
    if not me:
        gcom._back()
    p = pp.get(pid) or ({**m} if me else None)
    if not p:
        st.info("This member isn't in the community.")
        return
    mine_b, theirs_b = gcom._blocks(sc, m["gym_id"], m["id"])
    if pid in theirs_b:
        st.info("This profile isn't available.")
        return
    try:
        extra = sc.table("members").select("community_cover").eq("id", pid).limit(1).execute().data or [{}]
        cover = extra[0].get("community_cover")
    except Exception:
        cover = None
    try:
        posts = sc.table("community_posts").select("*").eq("gym_id", m["gym_id"]).eq("member_id", pid) \
            .eq("hidden", False).order("created_at", desc=True).limit(90).execute().data or []
    except Exception:
        posts = []
    ids = [x["id"] for x in posts]
    try:
        likes = sc.table("community_likes").select("post_id").in_("post_id", ids).execute().data or [] if ids else []
    except Exception:
        likes = []
    lk = {}
    for l in likes:
        lk[l["post_id"]] = lk.get(l["post_id"], 0) + 1
    try:
        tagged = [x for x in sc.table("community_posts").select("*").eq("gym_id", m["gym_id"]).eq("kind", "class")
                  .eq("hidden", False).order("created_at", desc=True).limit(120).execute().data or []
                  if pid in ((x.get("meta") or {}).get("tags") or [])]
    except Exception:
        tagged = []

    def tile(x):
        meta = x.get("meta") or {}
        return {"id": x["id"], "img": x.get("photo") or "", "text": gw._text(x.get("body"))[:120],
                "video": bool(meta.get("video")), "likes": lk.get(x["id"], 0), "pinned": bool(x.get("profile_pinned"))}
    tiles = sorted([tile(x) for x in posts], key=lambda t: not t["pinned"])
    fol, fing = gcom.followers_of(sc, m["gym_id"], pid), gcom.following_of(sc, m["gym_id"], pid)
    live = any(s.get("member_id") == pid for s in gcom.active_stories(sc, m["gym_id"]))
    chips, hot = [], False
    if ge.ready(sc):
        days = {t.date() for t in ge.visit_times(sc, m["gym_id"], pid)}
        sk = ge.streak(days)
        if sk["weeks"]:
            chips.append(f"🔥 {sk['weeks']}-week streak")
            hot = True
        chips += [b["label"] for b in ge.badges(sc, pid)[:4]]
    if p.get("buddy_goal") or p.get("fitness_goal"):
        chips.append(f"🎯 {p.get('buddy_goal') or p.get('fitness_goal')}")
    try:
        hl_rows = [r for r in sc.table("community_stories").select("*").eq("member_id", pid)
                   .order("created_at", desc=True).limit(300).execute().data or [] if r.get("highlight")]
    except Exception:
        hl_rows = []
    highlights, seen = [], set()
    for h in hl_rows:
        if h.get("highlight") and h["highlight"] not in seen:
            seen.add(h["highlight"])
            highlights.append({"name": h["highlight"], "cover": h.get("photo") or ""})
    data = {"profile": {"me": me, "name": gw._text(p.get("full_name"), "Member"), "handle": handle_of(p.get("full_name")),
                        "avatar": p.get("photo") or "", "initials": gw.initials(p.get("full_name")), "cover": cover or "",
                        "bio": gw._text(p.get("community_bio")), "chips": chips, "hot": hot, "live": live,
                        "following": pid in gcom.following_of(sc, m["gym_id"], m["id"]), "blocked": pid in mine_b,
                        "stats": {"posts": len(posts), "followers": len(fol), "following": len(fing),
                                  "likes": sum(lk.values())}},
            "highlights": highlights, "posts": tiles, "tagged": [tile(x) for x in tagged]}
    evt = profile_view(data, key=f"gp_prof_{pid}")
    if not evt:
        return
    kind, val = evt
    if kind == "followers":
        gcom.people_dialog(sc, m, "Followers", fol)
    elif kind == "following":
        gcom.people_dialog(sc, m, "Following", fing)
    elif kind == "edit":
        gcom.edit_profile_dialog(sc, m)
    elif kind in ("archive",):
        gcom.archive_dialog(sc, m)
    elif kind == "newstory":
        gcom.add_story_dialog(sc, m)
    elif kind == "follow":
        gcom.toggle_follow(sc, m, pid)
        st.rerun()
    elif kind == "message":
        gcom._open_chat(pid)
        st.rerun()
    elif kind in ("more", "block"):
        more_dialog(sc, m, pid, p, pid in mine_b)
    elif kind == "story":
        groups = {pid: [s for s in gcom.active_stories(sc, m["gym_id"]) if s.get("member_id") == pid]}
        if groups[pid]:
            st.session_state["cm_story_pos"] = [0, 0]
            gcom.story_dialog(sc, m, [pid], groups, gym_name)
    elif kind == "highlight":
        rows = [s for s in (sc.table("community_stories").select("*").eq("member_id", pid).eq("highlight", val)
                            .order("created_at").execute().data or [])]
        if rows:
            st.session_state["cm_story_pos"] = [0, 0]
            gcom.story_dialog(sc, m, [pid], {pid: rows}, gym_name)
    elif kind == "post":
        post_dialog(sc, m, val, gym_name, mine=me)


@st.dialog("Post")
def post_dialog(sc, m, post_id, gym_name, mine=False):
    import gympulse_community as gcom
    feed = [x for x in gcom.load_feed(sc, m["gym_id"], 300) if x["id"] == post_id]
    if not feed:
        st.info("This post is no longer available.")
        return
    gcom._post_card(sc, m, feed[0], gym_name)
    if mine:
        try:
            pinned = bool((sc.table("community_posts").select("profile_pinned").eq("id", post_id).limit(1)
                           .execute().data or [{}])[0].get("profile_pinned"))
        except Exception:
            return
        if st.button("Unpin from profile" if pinned else "📌 Pin to top of profile", key=f"pf_pin_{post_id}"):
            sc.table("community_posts").update({"profile_pinned": not pinned}).eq("id", post_id) \
                .eq("member_id", m["id"]).execute()
            st.rerun()


@st.dialog("More")
def more_dialog(sc, m, pid, p, blocked):
    import gympulse_community as gcom
    name = gw._text(p.get("full_name"), "this member")
    if st.button(f"Unblock {name}" if blocked else f"Block {name}", key="pf_block", use_container_width=True):
        if blocked:
            sc.table("community_blocks").delete().eq("blocker_id", m["id"]).eq("blocked_id", pid).execute()
        else:
            sc.table("community_blocks").insert({"gym_id": m["gym_id"], "blocker_id": m["id"], "blocked_id": pid}).execute()
            sc.table("community_follows").delete().eq("follower_id", m["id"]).eq("followee_id", pid).execute()
            sc.table("community_follows").delete().eq("follower_id", pid).eq("followee_id", m["id"]).execute()
        gcom._bust(m["gym_id"])
        st.rerun()
    if st.button("Report profile", key="pf_report", use_container_width=True):
        try:
            sc.table("community_reports").insert({"gym_id": m["gym_id"], "member_id": m["id"],
                                                  "reason": f"Profile reported: {name}"}).execute()
        except Exception:
            pass
        st.success("Thanks. The gym will take a look.")


def save_cover(sc, m, raw):
    """Resize a cover photo (1500 × 600) and save it."""
    import io
    import gympulse_community as gcom
    from PIL import Image, ImageOps
    img = ImageOps.fit(ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB"), (1500, 600))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=82, optimize=True)
    url = gcom._store_photo(sc, m["gym_id"], out.getvalue())
    sc.table("members").update({"community_cover": url}).eq("id", m["id"]).execute()
    return url
