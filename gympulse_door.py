"""GymPulse AI · Door access: paid members get in, others are stopped at the door.

How it fits together (sql/phase45_door_access.sql):
  - A reader at the door (QR scanner, card or key-fob reader) types the member's code into the door screen
    (usegympulseai.com/?door=<device key>, open on a tablet at the entrance), or a door controller calls the
    door-access web link (supabase/functions/door-access).
  - door_check() decides: active membership (plus the gym's grace days) or valid HMO cover gets in; unknown,
    archived, suspended, frozen, no plan or expired is refused, with the reason. Every attempt is logged, and
    each entry counts as a check-in, so attendance and risk scores update by themselves.
  - Optional door opener link: when a member is let in, GymPulse calls it to release the lock (for example a
    smart relay's cloud link). The gym's own electrician fits the lock and relay.
"""
import time
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

import gympulse_workspaces as gw

SQL_HINT = "Door access needs a one-time setup: run sql/phase45_door_access.sql in Supabase."


def device_key(supabase, gym_id):
    try:
        row = supabase.table("gyms").select("device_key").eq("id", gym_id).limit(1).execute().data or []
        return (row[0].get("device_key") if row else "") or ""
    except Exception:
        return ""


def config(supabase, gym_id):
    """{enabled, grace_days, opener_url}, or None when phase 45 hasn't been run."""
    try:
        rows = supabase.table("door_config").select("*").eq("gym_id", gym_id).limit(1).execute().data or []
    except Exception:
        return None
    r = rows[0] if rows else {}
    return {"enabled": r.get("enabled", True) is not False, "grace_days": int(r.get("grace_days") or 0),
            "opener_url": r.get("opener_url") or ""}


def screen_url(key):
    return f"{gw.APP_URL}/?door={key}"


def controller_url(key):
    try:
        base = str(st.secrets["SUPABASE_URL"]).rstrip("/")
    except Exception:
        base = "https://YOUR-PROJECT.supabase.co"
    return f"{base}/functions/v1/door-access?key={key}&code=MEMBERCODE"


def open_door(url):
    """Call the gym's door opener link (https only). Returns True when it answered."""
    if not url or not url.lower().startswith("https://"):
        return False
    try:
        return requests.get(url, timeout=4).status_code < 400
    except Exception:
        return False


# ------------------------------------------------------------------ the door screen (tablet at the entrance)
DOOR_CSS = """<style>
html body .stApp { background: #0A0F1E !important; }
.door-wrap { max-width: 720px; margin: 0 auto; text-align: center; }
.door-gym { color: #93A1B8; font-size: 18px; margin: 8px 0 22px; }
.door-card { border-radius: 8px; padding: 44px 24px; margin: 18px 0; }
.door-card.ok { background: #B7F34A; color: #0A0F1E; }
.door-card.no { background: #E5484D; color: #FFFFFF; }
.door-card.idle { border: 1px solid rgba(255,255,255,0.14); color: #F4F7FB; }
.door-big { font-size: 44px; font-weight: 600; letter-spacing: -0.02em; line-height: 1.1; }
.door-sub { font-size: 20px; margin-top: 10px; }
html body .stApp [data-testid="stForm"] { max-width: 720px; margin: 0 auto; border: 0 !important; padding: 0 !important; }
html body .stApp [data-testid="InputInstructions"] { display: none !important; }
</style>"""


def _focus_input():
    import streamlit.components.v1 as components
    components.html("""<script>
      const f = () => { const i = window.parent.document.querySelector('input[aria-label="Member code"]');
                        if (i && window.parent.document.activeElement !== i) i.focus(); };
      f(); setInterval(f, 1500);
    </script>""", height=0)


def render_screen(supabase, key):
    """Full-screen door page. Card, fob and QR readers type the code and press Enter."""
    st.markdown(DOOR_CSS, unsafe_allow_html=True)
    gym = ""
    try:
        r = supabase.rpc("door_gym_name", {"p_device_key": key}).execute().data
        gym = r if isinstance(r, str) else ""
    except Exception:
        gym = ""
    gw._md(f'<div class="door-wrap"><div class="door-gym">{gw._esc(gym or "Door")} · scan your card or code</div></div>')
    last = st.session_state.get("door_last")
    if last and time.time() - last["t"] > 6:
        last = None
    if last:
        if last.get("error"):
            card = ('no', "This door screen isn't set up", "Ask the gym to open the door screen link again.")
        elif last["allow"]:
            first = (last.get("name") or "").split(" ")[0]
            until = f' · until {pd.Timestamp(last["until"]):%d %b %Y}' if last.get("until") else ""
            card = ("ok", f"Welcome{', ' + gw._esc(first) if first else ''}", f"Come in{until}")
        else:
            card = ("no", "Please see the front desk", gw._esc(last.get("reason") or "Not allowed in"))
    else:
        card = ("idle", "Ready", "Hold your card, fob or QR code to the reader")
    gw._md(f'<div class="door-wrap"><div class="door-card {card[0]}"><div class="door-big">{card[1]}</div>'
           f'<div class="door-sub">{card[2]}</div></div></div>')
    with st.form("door_form", clear_on_submit=True, border=False):
        code = st.text_input("Member code", placeholder="Scan or type the member code",
                             label_visibility="collapsed")
        go = st.form_submit_button("Check", use_container_width=True)
    _focus_input()
    if go and code.strip():
        try:
            res = supabase.rpc("door_check", {"p_device_key": key, "p_code": code.strip(),
                                              "p_door": "Door screen"}).execute().data or {}
        except Exception:
            res = {"ok": False, "error": "unavailable"}
        if res.get("ok") and res.get("allow") and res.get("opener"):
            open_door(res["opener"])
        st.session_state["door_last"] = {"t": time.time(), "allow": bool(res.get("allow")),
                                         "name": res.get("name"), "until": res.get("until"),
                                         "reason": res.get("reason"), "error": not res.get("ok")}
        st.rerun()
    if last:                                   # back to "Ready" a few seconds after each scan
        @st.fragment(run_every=2)
        def _reset():
            prev = st.session_state.get("door_last")
            if prev and time.time() - prev["t"] > 6:
                st.session_state.pop("door_last", None)
                st.rerun(scope="app")
        _reset()


# ------------------------------------------------------------------ owner settings
def render_settings(supabase, gym_id):
    cfg = config(supabase, gym_id)
    st.markdown("**Door access**")
    if cfg is None:
        st.info(SQL_HINT)
        return
    key = device_key(supabase, gym_id)
    st.caption("Let members with an active membership through the door and stop everyone else, with the reason. "
               "Each entry also counts as a check-in. You need a reader at the door, and an electric lock with a "
               "relay fitted by your electrician if you want the door to open by itself.")
    c1, c2 = st.columns(2)
    enabled = c1.toggle("Door access on", value=cfg["enabled"], key="door_on")
    grace = c2.number_input("Grace days after a plan ends", 0, 30, cfg["grace_days"], key="door_grace",
                            help="Members whose plan ended up to this many days ago still get in. 0 means none.")
    opener = st.text_input("Door opener link (optional)", value=cfg["opener_url"], key="door_opener",
                           placeholder="https://… the link that releases your lock",
                           help="When a member is let in, GymPulse calls this link to open the door. Smart relays "
                                "(for example Shelly) give you one in their app. Must start with https://.")
    if st.button("Save door settings", type="primary", key="door_save"):
        if opener.strip() and not opener.strip().lower().startswith("https://"):
            st.error("The door opener link must start with https://.")
        else:
            try:
                supabase.table("door_config").upsert({"gym_id": gym_id, "enabled": bool(enabled),
                                                      "grace_days": int(grace), "opener_url": opener.strip() or None,
                                                      "updated_at": datetime.utcnow().isoformat() + "Z"},
                                                     on_conflict="gym_id").execute()
                st.success("Door settings saved.")
            except Exception:
                st.error("Couldn't save. " + SQL_HINT)
    if cfg["opener_url"] and st.button("Test the door opener", key="door_test_btn"):
        st.success("The door opener answered.") if open_door(cfg["opener_url"]) else \
            st.error("The door opener didn't answer. Check the link and that the relay is online.")

    if key:
        st.markdown("**Door screen**")
        st.caption("Open this link on a tablet or small computer at the entrance, with a QR, card or fob reader "
                   "plugged in. Keep it private: anyone with it can check members in.")
        st.code(screen_url(key), language="text")
        with st.expander("For door controllers that call a web address"):
            st.caption("Set the controller to call this address with the member's code. It answers with "
                       '{"allow": true or false, "reason": …}. Add &format=text to get just OPEN or DENY.')
            st.code(controller_url(key), language="text")

    _render_cards(supabase, gym_id)
    _render_log(supabase, gym_id)


def _render_cards(supabase, gym_id):
    with st.expander("Give a member a card or key fob"):
        st.caption("Members can always use the QR code on their profile. For a card or fob, scan it into the "
                   "box below to link it to the member.")
        members, _ = gw.fetch_members(supabase, gym_id, archived=False, include_photo=False)
        if members.empty:
            st.info("Add members first.")
            return
        names = dict(zip(members["id"], members["full_name"]))
        mid = st.selectbox("Member", list(names), format_func=lambda i: names.get(i, ""), index=None,
                           placeholder="Choose a member", key="door_card_member")
        card = st.text_input("Card or fob number", key="door_card_no", placeholder="Scan the card here")
        if st.button("Link card", key="door_card_save") and mid and card.strip():
            try:
                supabase.table("members").update({"door_card": card.strip()[:40]}).eq("id", mid).execute()
                st.success(f"Card linked to {names.get(mid, 'the member')}.")
            except Exception:
                st.error("Couldn't link the card. " + SQL_HINT)


def _render_log(supabase, gym_id):
    st.markdown("**At the door today**")
    try:
        since = pd.Timestamp(gw.today_local()).tz_localize(gw.APP_TZ).tz_convert("UTC").isoformat()
        rows = (supabase.table("door_events").select("member_id, allowed, reason, at").eq("gym_id", gym_id)
                .gte("at", since).order("at", desc=True).limit(200).execute().data or [])
    except Exception:
        rows = []
    if not rows:
        st.caption("No one at the door yet today.")
        return
    members, _ = gw.fetch_members(supabase, gym_id, archived=None, include_photo=False)
    names = dict(zip(members["id"], members["full_name"])) if not members.empty else {}
    let_in = sum(1 for r in rows if r["allowed"])
    st.caption(f"{let_in} let in · {len(rows) - let_in} stopped")
    gw.table([{"Time": f'{pd.Timestamp(r["at"]).tz_convert(gw.APP_TZ):%H:%M}',
               "Member": names.get(r.get("member_id"), "Unknown code"),
               "Result": "Let in" if r["allowed"] else "Stopped",
               "Reason": r["reason"]} for r in rows[:50]])
