#!/usr/bin/env python3
"""GymPulse AI door bridge for Hikvision access terminals.

Runs on any always-on computer inside the gym (mini PC, front-desk laptop), on the same network as the
Hikvision terminals. Python 3.8+ only, nothing to install.

Two ways of working ("mode" in bridge_config.json):

  "sync" (recommended, keeps working when the internet drops)
    Every few minutes the bridge downloads each member's paid-until date from GymPulse AI and writes it onto
    the terminal, adding new members by name and member code. The terminal then decides by itself: paid
    members open the door, expired ones are refused, with or without internet. Staff only scan the member's
    face, finger or card on the terminal once. Every entry is sent back to GymPulse AI as a check-in; entries
    made while the internet was down are kept in pending_events.json and sent when it's back.

  "remote" (live check on every tap, needs internet)
    The terminal asks the bridge on every tap ("remote verification"), and the bridge asks GymPulse AI.

Staff can also open the door from their phone on the gym's Wi-Fi, with no internet: open
http://<this computer's IP>:8099/open and enter a staff PIN (set in "staff" below). They can open the door, or
find a member and let them in (door opens and the member is checked in). Each opening is recorded and sent to
GymPulse AI. With internet, "Open door and check in" on a member's profile in GymPulse AI does the same: the
bridge collects it within 2 seconds ("public_key" below is GymPulse's public key, safe to keep here).

Each member's Employee No. on the terminal is their GymPulse member code (8 letters/numbers, shown on their
profile). In sync mode the bridge creates these for you.

Setup: see door_bridge/README.md. Settings live in bridge_config.json next to this file:
{
  "gympulse_link": "https://<project>.supabase.co/functions/v1/door-access?key=<your device key>",
  "mode": "sync",
  "sync_minutes": 3,
  "listen_port": 8099,
  "terminals": [
    {"ip": "192.168.1.64", "user": "admin", "password": "<terminal password>", "door": "Main door"}
  ],
  "staff": [{"name": "Front desk", "pin": "<4 to 8 digits>"}],
  "public_key": "<GymPulse public key, filled in by the download>"
}
The terminal passwords stay on this computer. They are never sent to GymPulse AI.
"""
import hmac
import html
import json
import logging
import os
import re
import secrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.environ.get("BRIDGE_CONFIG", os.path.join(HERE, "bridge_config.json"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("bridge")


def load_config():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("listen_port", 8099)
    cfg.setdefault("when_offline", "deny")
    cfg.setdefault("mode", "sync")
    cfg.setdefault("sync_minutes", 3)
    cfg.setdefault("terminals", [])
    return cfg


CFG = None
SEEN = {}                       # (terminal ip, serialNo) -> already answered (terminals may resend)
SEEN_LOCK = threading.Lock()


# ------------------------------------------------------------------ reading the terminal's event
def find_event(body: bytes, content_type: str):
    """The AccessControllerEvent dict from a JSON or multipart message, or None (heartbeats, pictures)."""
    texts = []
    if "multipart" in (content_type or "").lower():
        m = re.search(r'boundary="?([^";]+)"?', content_type)
        if m:
            for part in body.split(b"--" + m.group(1).encode()):
                head, _, data = part.partition(b"\r\n\r\n")
                if b"json" in head.lower() or data.strip().startswith(b"{"):
                    texts.append(data.strip().rstrip(b"-").strip())
    else:
        texts.append(body.strip())
    for t in texts:
        try:
            j = json.loads(t.decode("utf-8", "ignore"))
        except ValueError:
            continue
        ev = j.get("AccessControllerEvent") if isinstance(j, dict) else None
        if isinstance(ev, dict):
            return j, ev
    return None, None


def member_code(ev):
    for k in ("employeeNoString", "employeeNo", "cardNo"):
        v = str(ev.get(k) or "").strip()
        if v and v != "0":
            return v
    return ""


# ------------------------------------------------------------------ GymPulse and the terminal
def ask_gympulse(code, door):
    url = CFG["gympulse_link"] + "&" + urllib.parse.urlencode({"code": code, "door": door})
    try:
        with urllib.request.urlopen(url, timeout=4) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        log.warning("GymPulse AI not reachable (%s)", e)
        return None


def tell_terminal(term, serial, allow, info):
    """Remote mode: PUT /ISAPI/AccessControl/remoteCheck on the terminal, with the result."""
    body = {"RemoteCheck": {"serialNo": int(serial), "checkResult": "success" if allow else "failed",
                            "info": (info or "")[:32]}}
    status, _ = isapi(term, "PUT", "/ISAPI/AccessControl/remoteCheck?format=json", body, timeout=4)
    return 200 <= status < 300


# ------------------------------------------------------------------ talking to a terminal (digest login)
def isapi(term, method, path, payload=None, timeout=6, xml=None):
    """(status, json reply or {}) for one ISAPI call. status 0 means the terminal didn't answer."""
    url = f"http://{term['ip']}{path}"
    pm = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    pm.add_password(None, f"http://{term['ip']}/", term.get("user", "admin"), term.get("password", ""))
    opener = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(pm))
    if xml is not None:
        data, ctype = xml.encode(), "application/xml"
    else:
        data, ctype = (json.dumps(payload).encode() if payload is not None else None), "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": ctype})
    try:
        with opener.open(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "ignore")
            status = r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read().decode("utf-8", "ignore"), e.code
    except Exception as e:
        log.warning("Terminal %s did not answer (%s)", term["ip"], e)
        return 0, {}
    try:
        return status, json.loads(raw) if raw.strip() else {}
    except ValueError:
        return status, {}


def _ok(status, reply):
    return 200 <= status < 300 and str(reply.get("statusCode", 1)) == "1"


# ------------------------------------------------------------------ sync mode: paid-until dates on the terminal
STATE_FILE = os.path.join(HERE, "sync_state.json")
ROSTER_FILE = os.path.join(HERE, "roster_cache.json")       # the member list, for the staff page offline
PENDING_FILE = os.path.join(HERE, "pending_events.json")
PENDING_LOCK = threading.Lock()
BLOCKED_END = "2020-01-01T23:59:59"           # a date in the past: the terminal refuses this person
EXIT_END = "2037-12-31T23:59:59"              # exit doors always open
PASS_MINORS = {1, 2, 38, 40, 75}               # card, card+PIN, fingerprint, card+fingerprint, face: let in


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def fetch_roster():
    try:
        with urllib.request.urlopen(CFG["gympulse_link"] + "&action=roster", timeout=20) as r:
            res = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        log.warning("GymPulse AI not reachable, the terminal keeps its last dates (%s)", e)
        return None
    if not res.get("ok"):
        log.warning("GymPulse AI refused the door link. Download a new config file from Settings.")
        return None
    return res.get("members") or []


def user_payload(code, name, end):
    return {"UserInfo": {
        "employeeNo": code, "name": (name or code).encode("utf-8")[:32].decode("utf-8", "ignore"),
        "userType": "normal",
        "Valid": {"enable": True, "beginTime": "2020-01-01T00:00:00", "endTime": end, "timeType": "local"},
        "doorRight": "1", "RightPlan": [{"doorNo": 1, "planTemplateNo": "1"}]}}


def push_user(term, code, name, end):
    """True when written, False when the terminal refused this member, None when it didn't answer."""
    body = user_payload(code, name, end)
    for method, path in (("PUT", "/ISAPI/AccessControl/UserInfo/SetUp?format=json"),
                         ("PUT", "/ISAPI/AccessControl/UserInfo/Modify?format=json"),
                         ("POST", "/ISAPI/AccessControl/UserInfo/Record?format=json")):
        status, reply = isapi(term, method, path, body)
        if status == 0:
            return None
        if _ok(status, reply):
            return True
    log.warning("Terminal %s refused member %s: %s", term["ip"], code, reply.get("subStatusCode", status))
    return False


def push_card(term, code, card):
    body = {"CardInfo": {"employeeNo": code, "cardNo": card, "cardType": "normalCard"}}
    for method, path in (("PUT", "/ISAPI/AccessControl/CardInfo/SetUp?format=json"),
                         ("POST", "/ISAPI/AccessControl/CardInfo/Record?format=json")):
        status, reply = isapi(term, method, path, body)
        if status == 0:
            return False
        if _ok(status, reply) or "exist" in str(reply.get("subStatusCode", "")).lower():
            return True
    return False


def sync_terminal(term, members, state):
    """Write new or changed members onto one terminal. state: {code: what we last wrote}."""
    exit_door = "exit" in term.get("door", "").lower()
    wanted = {}
    for m in members:
        code = str(m.get("code") or "").upper()
        if not code:
            continue
        until = m.get("until")
        end = EXIT_END if exit_door else (f"{until}T23:59:59" if until else BLOCKED_END)
        wanted[code] = (m.get("name") or "", end, m.get("card") or "")
    if not exit_door:                                    # archived or deleted since the last sync: refuse
        for code, sig in state.items():
            if code not in wanted and sig[1] != BLOCKED_END:
                wanted[code] = (sig[0], BLOCKED_END, "")
    changed = 0
    for code, (name, end, card) in wanted.items():
        old = state.get(code)
        if old and old[0] == name and old[1] == end and (not card or old[2] == card):
            continue
        done = push_user(term, code, name, end)
        if done is None:
            break                                        # terminal unreachable: try again next round
        if not done:
            continue
        if card and (not old or old[2] != card) and not push_card(term, code, card):
            card = old[2] if old else ""
        state[code] = [name, end, card]
        changed += 1
    return changed


def sync_loop():
    full_every = 24 * 60 * 60
    last_full = 0
    while True:
        members = fetch_roster()
        if members is not None:
            _write_json(ROSTER_FILE, {"saved": time.strftime("%d %b, %H:%M"), "members": members})
            all_state = _read_json(STATE_FILE, {})
            if time.time() - last_full > full_every:      # once a day, write everyone again
                all_state, last_full = {}, time.time()
            for term in CFG["terminals"]:
                st = all_state.setdefault(term["ip"], {})
                n = sync_terminal(term, members, st)
                if n:
                    log.info("Terminal %s (%s): updated %d member(s)", term["ip"], term.get("door"), n)
            _write_json(STATE_FILE, all_state)
        time.sleep(max(1, float(CFG["sync_minutes"])) * 60)


def queue_event(term, ev):
    """An entry the terminal decided by itself: keep it until GymPulse AI has it."""
    code = member_code(ev)
    if not code or int(ev.get("majorEventType") or ev.get("major") or 5) != 5:
        return
    minor = int(ev.get("subEventType") or ev.get("minor") or 0)
    allowed = minor in set(CFG.get("pass_minors") or PASS_MINORS)
    at = ev.get("dateTime") or time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with PENDING_LOCK:
        pending = _read_json(PENDING_FILE, [])
        pending.append({"code": code, "door": term.get("door", "Main door"), "allowed": allowed, "at": at})
        _write_json(PENDING_FILE, pending[-20000:])
    log.info("%s %s code=%s -> %s", term.get("door"), term["ip"], code, "LET IN" if allowed else "REFUSED")


def send_loop():
    while True:
        time.sleep(15)
        with PENDING_LOCK:
            pending = _read_json(PENDING_FILE, [])
        if not pending:
            continue
        batch = pending[:200]
        req = urllib.request.Request(CFG["gympulse_link"] + "&action=record", method="POST",
                                     data=json.dumps({"events": batch}).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                ok = json.loads(r.read().decode("utf-8")).get("ok")
        except Exception as e:
            log.info("Holding %d entr%s until the internet is back (%s)", len(pending),
                     "y" if len(pending) == 1 else "ies", e)
            continue
        if ok:
            with PENDING_LOCK:
                rest = _read_json(PENDING_FILE, [])[len(batch):]
                _write_json(PENDING_FILE, rest)


# ------------------------------------------------------------------ staff open the door from their phone (gym Wi-Fi)
SESSIONS = {}                                   # token -> (staff name, expires at)
FAILS = {}                                      # phone IP -> [times of wrong PINs]
LAST_OPEN = {}                                  # door name -> (time, staff name)
STAFF_LOCK = threading.Lock()
SESSION_HOURS = 12

OPEN_XML = ('<RemoteControlDoor version="2.0" xmlns="http://www.isapi.org/ver20/XMLSchema">'
            '<cmd>open</cmd></RemoteControlDoor>')


def staff_list():
    out = []
    for s in CFG.get("staff") or []:
        pin = str(s.get("pin") or "")
        if pin.isdigit() and 4 <= len(pin) <= 8:
            out.append({"name": str(s.get("name") or "Staff")[:40], "pin": pin})
    return out


def entry_doors():
    return [t for t in CFG["terminals"] if "exit" not in t.get("door", "").lower()] or CFG["terminals"]


def open_door(term, staff_name, member=None, record=True):
    """Open the door. member: {"code", "name"} when staff let a member in (they're checked in too).
    record=False when GymPulse AI already logs it (commands from a member's profile)."""
    status, _ = isapi(term, "PUT", "/ISAPI/AccessControl/RemoteControl/door/1", xml=OPEN_XML, timeout=4)
    if not 200 <= status < 300:
        status, _ = isapi(term, "PUT", "/ISAPI/AccessControl/RemoteControl/door/1?format=json",
                          {"RemoteControlDoor": {"cmd": "open"}}, timeout=4)
    ok = 200 <= status < 300
    door = term.get("door", "Main door")
    if ok:
        LAST_OPEN[door] = (time.time(), staff_name, (member or {}).get("name"))
        if record:
            at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            event = ({"code": member["code"], "door": door, "allowed": True, "at": at, "by": staff_name}
                     if member else {"staff": staff_name, "door": door, "at": at})
            with PENDING_LOCK:
                pending = _read_json(PENDING_FILE, [])
                pending.append(event)
                _write_json(PENDING_FILE, pending[-20000:])
    who = f"{member.get('name')} let in by {staff_name}" if member else f"opened by staff ({staff_name})"
    log.info("%s %s -> %s", door, who, "OPEN" if ok else "terminal did not answer")
    return ok


# ------------------------------------------------------------------ "Open door and check in" from GymPulse AI
def _rest(fn, body):
    base = CFG["gympulse_link"].split("/functions/v1/")[0]
    key = CFG.get("public_key") or ""
    req = urllib.request.Request(f"{base}/rest/v1/rpc/{fn}", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "apikey": key,
                                          "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode("utf-8"))


def device_key():
    q = urllib.parse.parse_qs(urllib.parse.urlparse(CFG["gympulse_link"]).query)
    return (q.get("key") or [""])[0]


def command_loop():
    """Every 2 seconds: any "Open door and check in" taps from GymPulse AI? Open the door and report back."""
    key = device_key()
    quiet_until = 0
    while True:
        time.sleep(2)
        try:
            res = _rest("door_commands_take", {"p_device_key": key})
        except Exception as e:
            if time.time() > quiet_until:
                log.info("Can't reach GymPulse AI for door taps (%s). Staff can use the phone page.", e)
                quiet_until = time.time() + 600
            time.sleep(8)
            continue
        for cmd in (res or {}).get("commands") or []:
            doors = entry_doors()
            term = next((t for t in doors if t.get("door") == cmd.get("door")), doors[0] if doors else None)
            ok = bool(term) and open_door(term, cmd.get("by") or "Staff",
                                          {"code": "", "name": cmd.get("name")} if cmd.get("name") else None,
                                          record=False)
            try:
                _rest("door_command_done", {"p_device_key": key, "p_id": cmd["id"], "p_ok": ok,
                                            "p_note": None if ok else "The door terminal didn't answer"})
            except Exception as e:
                log.warning("Opened the door but couldn't tell GymPulse AI (%s)", e)


def check_pin(ip, pin):
    """The staff member's name, None for a wrong PIN, or 'LOCKED' after 5 wrong PINs in 5 minutes."""
    now = time.time()
    with STAFF_LOCK:
        recent = [t for t in FAILS.get(ip, []) if now - t < 300]
        FAILS[ip] = recent
        if len(recent) >= 5:
            return "LOCKED"
        for s in staff_list():
            if hmac.compare_digest(s["pin"], str(pin or "")):
                FAILS.pop(ip, None)
                return s["name"]
        recent.append(now)
    return None


def session_name(cookie_header):
    m = re.search(r"gp_staff=([A-Za-z0-9_\-]+)", cookie_header or "")
    if not m:
        return None
    with STAFF_LOCK:
        name, until = SESSIONS.get(m.group(1), (None, 0))
    return name if until > time.time() else None


PAGE_CSS = """
:root{--navy:#10213F;--panel:#162A4D;--key:#1D3561;--keyon:#27447A;--line:#294069;--ink:#EEF1F6;--mute:#9DAAC2;
--dim:#7385A4;--lime:#C5F04A;--red:#FF8B7E}
*{box-sizing:border-box}html,body{margin:0;background:var(--navy);color:var(--ink)}
body{font:16px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;min-height:100dvh;display:flex;
flex-direction:column;align-items:center;padding:max(14px,env(safe-area-inset-top)) max(16px,env(safe-area-inset-left))
calc(18px + env(safe-area-inset-bottom)) max(16px,env(safe-area-inset-right));-webkit-tap-highlight-color:transparent}
.col{width:100%;max-width:440px;display:flex;flex-direction:column;flex:1}
.bar{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:6px 0 18px;
border-bottom:1px solid var(--line);font-size:15px}
.bar b{font-weight:600}.bar span{color:var(--mute)}.bar a{color:var(--mute);text-decoration:none;margin-left:12px;
padding:8px 0;border-bottom:1px solid var(--line)}
.err{color:var(--red);margin:14px 0 0}
input{font-family:inherit}
button,a,input{outline-offset:2px}button:focus-visible,a:focus-visible,input:focus-visible{outline:3px solid var(--lime)}
/* PIN keypad */
.pinhead{padding:36px 0 20px}.pinhead p{margin:0;color:var(--mute)}
.pinhead h1{font-size:26px;font-weight:600;letter-spacing:-.01em;margin:0 0 6px}
.dots{display:flex;gap:14px;height:22px;align-items:center;margin:8px 0 26px}
.dots i{width:14px;height:14px;border-radius:50%;border:2px solid var(--dim)}.dots i.on{background:var(--ink);
border-color:var(--ink)}
#pin{position:absolute;left:-9999px}
.pad{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:auto}
.pad button{height:68px;border:0;border-radius:12px;background:var(--key);color:var(--ink);font-family:inherit;font-size:26px;font-weight:500;line-height:1;
font-variant-numeric:tabular-nums;cursor:pointer}
.pad button:active{background:var(--keyon)}
.pad .fn{font-size:16px;font-weight:500;color:var(--mute);background:transparent}
.pad .go{background:var(--ink);color:var(--navy);font-size:17px;font-weight:700}
.nojs{display:none}
/* Door */
.state{padding:28px 0 22px}.state small{display:block;color:var(--mute);font-size:14px;margin-bottom:4px}
.state div{font-size:28px;font-weight:600;letter-spacing:-.01em;line-height:1.15}
.state div.open{color:var(--lime)}.state div em{font-style:normal;color:var(--mute);font-weight:400;font-size:17px;
display:block;margin-top:4px}
.hold{position:relative;width:100%;height:76px;border:0;border-radius:14px;background:var(--lime);color:var(--navy);
font-family:inherit;font-size:20px;font-weight:700;line-height:1;cursor:pointer;overflow:hidden;touch-action:none;user-select:none;-webkit-user-select:none}
.hold span{position:relative;z-index:1}.hold small{display:block;font-size:13px;font-weight:500;margin-top:6px;
opacity:.75;position:relative;z-index:1}
.hold i{position:absolute;inset:0;background:#E3FA9A;transform:scaleX(0);transform-origin:left;transition:none}
.hold.go i{transform:scaleX(1);transition:transform .55s linear}
.find{margin:30px 0 0}.find label{display:block;color:var(--mute);font-size:14px;margin-bottom:8px}
.find input{width:100%;font-size:17px;padding:14px;border-radius:10px;border:1px solid var(--line);
background:var(--panel);color:var(--ink)}
.hit{display:flex;align-items:center;gap:12px;padding:13px 0;border-bottom:1px solid var(--line)}
.hit div{flex:1;min-width:0;display:grid}.hit b{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hit span{color:var(--mute);font-size:14px}.hit .warn{color:var(--red)}
.letin{flex:none;height:44px;padding:0 16px;border-radius:10px;border:1px solid var(--line);background:var(--panel);
color:var(--ink);font-family:inherit;font-size:15px;font-weight:600;line-height:1;cursor:pointer}
.hint{color:var(--dim);font-size:13px;margin:12px 0 0}
.none{color:var(--mute);margin:14px 0 0}
.doors{display:grid;gap:10px}
@media (prefers-reduced-motion:reduce){.hold.go i{transition:none}}
"""

PAGE_JS = """
document.querySelectorAll('.nojs').forEach(function(e){e.style.display='none'});
var pin=document.getElementById('pin'),dotbox=document.querySelector('.dots');
function draw(){if(!dotbox)return;var n=pin.value.length,h='';for(var i=0;i<Math.max(4,n);i++){h+='<i'+(i<n?' class="on"':'')+'></i>'}dotbox.innerHTML=h}
document.querySelectorAll('.pad [data-k]').forEach(function(b){b.addEventListener('click',function(){
 var k=b.dataset.k;if(k==='c'){pin.value=''}else if(k==='go'){if(pin.value.length>=4)pin.form.submit();return}
 else if(pin.value.length<8){pin.value+=k}draw()})});
if(pin){document.addEventListener('keydown',function(e){if(/^[0-9]$/.test(e.key)&&pin.value.length<8){pin.value+=e.key;draw()}
 else if(e.key==='Backspace'){pin.value=pin.value.slice(0,-1);draw()}else if(e.key==='Enter'&&pin.value.length>=4){pin.form.submit()}})}
document.querySelectorAll('.hold').forEach(function(b){var t;
 function start(e){e.preventDefault();b.classList.add('go');t=setTimeout(function(){b.form.submit()},550)}
 function stop(){clearTimeout(t);b.classList.remove('go')}
 b.addEventListener('pointerdown',start);['pointerup','pointerleave','pointercancel'].forEach(function(n){b.addEventListener(n,stop)});
 b.addEventListener('click',function(e){e.preventDefault()});
 b.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();b.form.submit()}})});
"""


def page(body):
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'>"
            "<meta name='robots' content='noindex'><meta name='theme-color' content='#10213F'>"
            "<title>Open door</title>"
            f"<style>{PAGE_CSS}</style></head><body><div class='col'>{body}</div>"
            f"<script>{PAGE_JS}</script></body></html>").encode("utf-8")


def _door_names():
    names = [t.get("door", "Main door") for t in entry_doors()]
    return names[0] if len(names) == 1 else "Gym doors"


def pin_page(msg="", err=True):
    head = f"<div class='bar'><b>{html.escape(_door_names())}</b><span>Staff only</span></div>"
    if not staff_list():
        return page(head + "<div class='pinhead'><h1>No staff PIN yet</h1><p>Add one under staff in "
                    "bridge_config.json on the gym computer, then restart the bridge.</p></div>")
    note = f"<p class='err'>{html.escape(msg)}</p>" if msg else ""
    keys = "".join(f"<button type='button' data-k='{k}'>{k}</button>" for k in "123456789")
    body = (head + "<div class='pinhead'><h1>Enter your PIN</h1><p>Works on the gym's Wi-Fi, even when the "
            "internet is down.</p>" + note + "</div>"
            "<form method='post' action='/open/pin'>"
            "<input id='pin' name='pin' type='password' inputmode='numeric' autocomplete='off' maxlength='8' "
            "aria-label='Staff PIN'>"
            "<div class='dots' aria-hidden='true'>" + "<i></i>" * 4 + "</div>"
            "<div class='pad'>" + keys +
            "<button type='button' class='fn' data-k='c'>Clear</button><button type='button' data-k='0'>0</button>"
            "<button type='button' class='go' data-k='go'>Enter</button></div>"
            "<noscript><p class='hint'>Type your PIN with the keyboard, then press Enter.</p>"
            "<style>#pin{position:static;width:100%;font-size:24px;padding:12px;margin:0 0 12px}</style></noscript>"
            "</form>")
    return page(body)


def _status(m, today):
    until = m.get("until")
    if not until:
        return "On hold or suspended", False
    if until >= today:
        return f"Paid until {time.strftime('%d %b', time.strptime(until, '%Y-%m-%d'))}", True
    return f"Expired {time.strftime('%d %b', time.strptime(until, '%Y-%m-%d'))}", False


def find_members(q, limit=8):
    q = (q or "").strip().lower()
    if len(q) < 2:
        return []
    members = (_read_json(ROSTER_FILE, {}) or {}).get("members") or []
    words = q.split()
    hits = [m for m in members if all(w in (m.get("name") or "").lower() or w in (m.get("code") or "").lower()
                                      for w in words)]
    return sorted(hits, key=lambda m: (not (m.get("name") or "").lower().startswith(q), m.get("name") or ""))[:limit]


def search_block(q):
    roster = _read_json(ROSTER_FILE, {}) or {}
    if not roster.get("members"):
        return ""
    today = time.strftime("%Y-%m-%d")
    out = ["<form class='find' method='get' action='/open'><label for='q'>Let a member in</label>"
           f"<input id='q' name='q' type='search' value='{html.escape(q or '')}' placeholder='Name or member code' "
           "autocomplete='off'></form>"]
    if q:
        hits = find_members(q)
        if not hits:
            out.append("<p class='none'>No member found. Check the spelling, or add them in GymPulse AI.</p>")
        for m in hits:
            label, ok = _status(m, today)
            out.append("<form class='hit' method='post' action='/open/member'>"
                       f"<input type='hidden' name='c' value='{html.escape(m.get('code') or '')}'>"
                       f"<div><b>{html.escape(m.get('name') or m.get('code') or '')}</b>"
                       f"<span class='{'' if ok else 'warn'}'>{html.escape(label)}</span></div>"
                       "<button class='letin' type='submit'>Let in</button></form>")
        out.append(f"<p class='hint'>Let in opens the door and checks them in. Member list updated "
                   f"{html.escape(roster.get('saved') or '')}.</p>")
    return "".join(out)


def door_page(name, msg="", err=False, q=""):
    doors = entry_doors()
    head = (f"<div class='bar'><b>{html.escape(_door_names())}</b><span>{html.escape(name)}"
            "<a href='/open/lock'>Lock</a></span></div>")
    states = []
    for t in doors:
        door = t.get("door", "Main door")
        last = LAST_OPEN.get(door)
        who = (f"{html.escape(last[2])}, let in by {html.escape(last[1])}" if last and last[2]
               else f"by {html.escape(last[1])}" if last else "")
        if last and time.time() - last[0] < 15:
            states.append((door, f"<div class='open'>Open<em>{who}, just now</em></div>"))
        elif last:
            states.append((door, f"<div>Locked<em>Last opened {time.strftime('%H:%M', time.localtime(last[0]))}, "
                                 f"{who}</em></div>"))
        else:
            states.append((door, "<div>Locked</div>"))
    note = f"<p class='err'>{html.escape(msg)}</p>" if msg else ""
    state_html = "".join(f"<div class='state'>{'' if len(states) == 1 else '<small>' + html.escape(d) + '</small>'}"
                         f"{st_}</div>" for d, st_ in states)
    holds = "".join(f"<form method='post' action='/open/door'><input type='hidden' name='d' value='{i}'>"
                    f"<button class='hold' type='submit'><i></i><span>Hold to open"
                    f"{'' if len(doors) == 1 else ' ' + html.escape(t.get('door', 'Main door'))}</span>"
                    "</button></form>" for i, t in enumerate(doors))
    return page(head + state_html + note + f"<div class='doors'>{holds}</div>" + search_block(q))


def handle(term, ev):
    if not ev.get("remoteCheck"):
        return                                           # an ordinary event, nothing to decide
    serial = ev.get("serialNo")
    if serial is None:
        return
    key = (term["ip"], serial)
    with SEEN_LOCK:
        if key in SEEN:
            return
        SEEN[key] = True
        if len(SEEN) > 5000:
            SEEN.clear()
    code = member_code(ev)
    door = term.get("door", "Main door")
    if not code:
        allow, info = False, "Not registered"
    else:
        res = ask_gympulse(code, door)
        if res is None or res.get("ok") is False:
            allow = CFG["when_offline"] == "allow" or "exit" in door.lower()
            info = "Offline" if res is None else "Check bridge setup"
        else:
            allow = bool(res.get("allow"))
            first = (res.get("name") or "").split(" ")[0]
            info = f"Welcome {first}".strip() if allow else (res.get("reason") or "See front desk")
    ok = tell_terminal(term, serial, allow, info)
    log.info("%s %s code=%s -> %s (%s)%s", door, term["ip"], code or "-", "OPEN" if allow else "DENY", info,
             "" if ok else " [terminal not answered]")


class Handler(BaseHTTPRequestHandler):
    def _term(self):
        ip = self.client_address[0]
        return next((t for t in CFG["terminals"] if str(t.get("ip", "")).split(":")[0] == ip), None)

    def _html(self, data, status=200, headers=()):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _go(self, where, headers=()):
        self.send_response(303)
        self.send_header("Location", where)
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()

    def _staff_post(self, body):
        form = urllib.parse.parse_qs(body.decode("utf-8", "ignore"))
        ip = self.client_address[0]
        if self.path.startswith("/open/pin"):
            who = check_pin(ip, (form.get("pin") or [""])[0])
            if who == "LOCKED":
                return self._html(pin_page("Too many wrong PINs. Try again in 5 minutes."))
            if not who:
                return self._html(pin_page("That PIN is not right."))
            token = secrets.token_urlsafe(24)
            with STAFF_LOCK:
                SESSIONS[token] = (who, time.time() + SESSION_HOURS * 3600)
            return self._go("/open", [("Set-Cookie", f"gp_staff={token}; Max-Age={SESSION_HOURS * 3600}; "
                                                     "Path=/open; HttpOnly; SameSite=Strict")])
        who = session_name(self.headers.get("Cookie"))
        if not who:
            return self._go("/open")
        doors = entry_doors()
        if self.path.startswith("/open/member"):
            code = (form.get("c") or [""])[0].upper()
            m = next((m for m in (_read_json(ROSTER_FILE, {}) or {}).get("members") or []
                      if (m.get("code") or "").upper() == code), None)
            if not m or not doors:
                return self._go("/open")
            if open_door(doors[0], who, {"code": m["code"], "name": m.get("name") or m["code"]}):
                return self._go("/open")
            return self._html(door_page(who, "The door terminal didn't answer. Check it has power and is on the "
                                             "Wi-Fi, or use the exit button.", err=True))
        try:
            term = doors[int((form.get("d") or ["0"])[0])]
        except (ValueError, IndexError):
            return self._go("/open")
        if open_door(term, who):
            return self._go("/open")                     # a page refresh won't open the door again
        return self._html(door_page(who, "The door terminal didn't answer. Check it has power and is on the "
                                         "Wi-Fi, or use the exit button.", err=True))

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path.startswith("/open/"):
            return self._staff_post(body)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"statusCode":1,"statusString":"OK"}')
        term = self._term()
        if not term:
            log.info("Ignored a message from %s (not in bridge_config.json)", self.client_address[0])
            return
        _, ev = find_event(body, self.headers.get("Content-Type", ""))
        if not ev:
            return
        if CFG["mode"] == "remote":
            threading.Thread(target=handle, args=(term, ev), daemon=True).start()
        else:
            key = (term["ip"], ev.get("serialNo"))
            with SEEN_LOCK:
                if ev.get("serialNo") is not None and key in SEEN:
                    return
                SEEN[key] = True
                if len(SEEN) > 5000:
                    SEEN.clear()
            queue_event(term, ev)

    def do_GET(self):
        if self.path.startswith("/open/lock"):
            m = re.search(r"gp_staff=([A-Za-z0-9_\-]+)", self.headers.get("Cookie") or "")
            if m:
                with STAFF_LOCK:
                    SESSIONS.pop(m.group(1), None)
            return self._go("/open", [("Set-Cookie", "gp_staff=; Max-Age=0; Path=/open; HttpOnly; SameSite=Strict")])
        if self.path.startswith("/open"):
            who = session_name(self.headers.get("Cookie"))
            q = (urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("q") or [""])[0][:60]
            return self._html(door_page(who, q=q) if who else pin_page())
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"GymPulse AI door bridge is running")

    def log_message(self, *args):
        pass


def main():
    global CFG
    CFG = load_config()
    if "door-access?key=" not in CFG.get("gympulse_link", ""):
        sys.exit("Put your GymPulse door link in bridge_config.json (Settings -> Check-in devices -> Door access).")
    port = int(CFG["listen_port"])
    if CFG["mode"] != "remote":
        threading.Thread(target=sync_loop, daemon=True).start()
    threading.Thread(target=send_loop, daemon=True).start()        # entries and staff openings
    if CFG.get("public_key"):
        threading.Thread(target=command_loop, daemon=True).start()  # "Open door and check in" from GymPulse AI
    if staff_list():
        log.info("Staff can open the door at http://<this computer's IP>:%s/open on the gym's Wi-Fi", port)
    log.info("GymPulse AI door bridge (%s mode) listening on port %s for %d terminal(s)", CFG["mode"], port,
             len(CFG["terminals"]))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
