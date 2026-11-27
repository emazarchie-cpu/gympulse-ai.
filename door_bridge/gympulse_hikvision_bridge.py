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
  ]
}
The terminal passwords stay on this computer. They are never sent to GymPulse AI.
"""
import json
import logging
import os
import re
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
def isapi(term, method, path, payload=None, timeout=6):
    """(status, json reply or {}) for one ISAPI call. status 0 means the terminal didn't answer."""
    url = f"http://{term['ip']}{path}"
    pm = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    pm.add_password(None, f"http://{term['ip']}/", term.get("user", "admin"), term.get("password", ""))
    opener = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(pm))
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
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

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
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
        threading.Thread(target=send_loop, daemon=True).start()
    log.info("GymPulse AI door bridge (%s mode) listening on port %s for %d terminal(s)", CFG["mode"], port,
             len(CFG["terminals"]))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
