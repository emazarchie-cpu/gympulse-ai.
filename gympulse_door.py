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
            "opener_url": r.get("opener_url") or "", "renew_message": r.get("renew_message", True) is not False}


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
    enabled = c1.toggle("Door access on", value=cfg["enabled"], key="door_on",
                        help="Off: devices and the door screen only record visits, and nobody is stopped.")
    grace = c2.number_input("Grace days after a plan ends", 0, 30, cfg["grace_days"], key="door_grace",
                            help="Members whose plan ended up to this many days ago still get in. 0 means none.")
    opener = st.text_input("Door opener link (optional)", value=cfg["opener_url"], key="door_opener",
                           placeholder="https://… the link that releases your lock",
                           help="When a member is let in, GymPulse calls this link to open the door. Smart relays "
                                "(for example Shelly) give you one in their app. Must start with https://.")
    renew = st.toggle("Send the renewal message to members stopped because their plan expired",
                      value=cfg["renew_message"], key="door_renew",
                      help="Within about 10 minutes, by WhatsApp and/or email (as set in Grow → Automatic "
                           "messages), with their pay link. Once a day at most.")
    if st.button("Save door settings", type="primary", key="door_save"):
        if opener.strip() and not opener.strip().lower().startswith("https://"):
            st.error("The door opener link must start with https://.")
        else:
            try:
                supabase.table("door_config").upsert({"gym_id": gym_id, "enabled": bool(enabled),
                                                      "grace_days": int(grace), "opener_url": opener.strip() or None,
                                                      "renew_message": bool(renew),
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

    with st.expander("Which door hardware?"):
        st.markdown(
            "- **Phone:** members open their QR code in the member app and hold it to a QR reader at the door. "
            "Cheapest, and it works with the door screen today.\n"
            "- **No phone:** a card or key fob, linked to the member below. Card readers work with the door screen "
            "today.\n"
            "- **Fingerprint or face:** a Hikvision terminal with remote verification is connected (see "
            "Hikvision terminals below). For other brands, tell us the exact model before you buy.\n"
            "- **Leaving:** name a reader \"Exit\" and it always opens, for fire safety, and records who left.")
        st.caption("Phone tap (NFC or Bluetooth, like some imported systems) needs that brand's own readers "
                   "and app, and isn't connected yet.")
    if key:
        _render_hikvision(key)
    _render_cards(supabase, gym_id)
    _render_log(supabase, gym_id)


BRIDGE_DIR = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)),
                                       "door_bridge")


def bridge_config(key):
    import json
    link = controller_url(key).split("&code=")[0]
    return json.dumps({"gympulse_link": link, "listen_port": 8099, "when_offline": "deny",
                       "terminals": [{"ip": "192.168.1.64", "user": "admin", "password": "TERMINAL PASSWORD",
                                      "door": "Main door"},
                                     {"ip": "192.168.1.65", "user": "admin", "password": "TERMINAL PASSWORD",
                                      "door": "Exit"}]}, indent=2)


def _render_hikvision(key):
    import os
    with st.expander("Hikvision terminals (fingerprint, face or card)"):
        st.markdown("**How it works:** a member puts their finger, face or card on the terminal. GymPulse checks "
                    "their membership. Paid members get in. Others see why on the screen.")
        st.markdown("**You need:** a Hikvision terminal with *Remote Verification*, an electric lock fitted by your "
                    "installer, and one computer at the gym that stays on.")
        st.markdown("**Set it up in 4 steps**\n\n"
                    "1. **Download** the 3 files below onto that computer. Put them in one folder.\n"
                    "2. **Open the config file.** Type each terminal's IP address and password. Call the door "
                    "people leave through **Exit**: it always opens.\n"
                    "3. **On each terminal**, turn on *Remote Verification*. Under *HTTP Listening*, enter the "
                    "computer's IP address and port **8099**.\n"
                    "4. **Start the bridge** by double-clicking it, or run `python3 gympulse_hikvision_bridge.py`.")
        st.markdown("**Add members to the terminal:** use their GymPulse member code (on their profile) as the "
                    "*Employee No.*, then scan their finger, face or card.")
        c1, c2, c3 = st.columns(3)
        try:
            code = open(os.path.join(BRIDGE_DIR, "gympulse_hikvision_bridge.py"), encoding="utf-8").read()
            guide = open(os.path.join(BRIDGE_DIR, "README.md"), encoding="utf-8").read()
        except OSError:
            code, guide = "", ""
        c1.download_button("Bridge program", code, "gympulse_hikvision_bridge.py", "text/x-python",
                           use_container_width=True, key="door_dl_bridge", disabled=not code)
        c2.download_button("Config file", bridge_config(key), "bridge_config.json", "application/json",
                           use_container_width=True, key="door_dl_cfg")
        c3.download_button("Setup guide", guide, "GymPulse door bridge guide.md", "text/markdown",
                           use_container_width=True, key="door_dl_guide", disabled=not guide)
        st.caption("Keep the config file private: it holds your door link. Give the setup guide to your installer.")


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
    left = sum(1 for r in rows if r["reason"] == "Left the gym")
    let_in = sum(1 for r in rows if r["allowed"]) - left
    st.caption(f"{let_in} let in · {len(rows) - let_in - left} stopped · {left} left")
    gw.table([{"Time": f'{pd.Timestamp(r["at"]).tz_convert(gw.APP_TZ):%H:%M}',
               "Member": names.get(r.get("member_id"), "Unknown code"),
               "Result": "Left" if r["reason"] == "Left the gym" else "Let in" if r["allowed"] else "Stopped",
               "Reason": r["reason"]} for r in rows[:50]])


# ------------------------------------------------------------------ the member's door pass (any phone)
def door_pass_png(name, gym, code):
    """A phone-sized picture with the member's QR code: saved in their photos, it works on any phone,
    even with no internet. The QR holds the member code, like the one on their profile."""
    import io
    import os
    import qrcode
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1080, 1920
    NAVY, TEXT, MUTED, LIME = (10, 15, 30), (244, 247, 251), (147, 161, 184), (183, 243, 74)
    img = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(img)
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")

    def font(bold, size):
        for f in (("InstrumentSans-Bold.ttf" if bold else "InstrumentSans-Regular.ttf"), "DejaVuSans.ttf"):
            try:
                return ImageFont.truetype(os.path.join(base, f) if "Instrument" in f else f, size)
            except OSError:
                continue
        return ImageFont.load_default()

    def centre(y, text, f, fill):
        w = d.textlength(text, font=f)
        d.text(((W - w) / 2, y), text, font=f, fill=fill)

    centre(170, (gym or "Your gym")[:30], font(False, 46), MUTED)
    centre(240, "Door pass", font(True, 92), TEXT)
    q = qrcode.QRCode(border=2, box_size=10, error_correction=qrcode.constants.ERROR_CORRECT_M)
    q.add_data(code)
    q.make(fit=True)
    qr = q.make_image(fill_color="black", back_color="white").convert("RGB").resize((760, 760), Image.NEAREST)
    d.rounded_rectangle((140, 440, 940, 1240), radius=28, fill=(255, 255, 255))
    img.paste(qr, (160, 460))
    centre(1300, (name or "Member")[:28], font(True, 64), TEXT)
    centre(1390, f"Code {code}", font(False, 48), LIME)
    centre(1560, "Hold this to the reader at the door.", font(False, 40), MUTED)
    centre(1615, "Turn your screen brightness up.", font(False, 40), MUTED)
    centre(1800, "GymPulse AI", font(False, 34), MUTED)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
