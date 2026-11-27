#!/usr/bin/env python3
"""GymPulse AI door bridge for Hikvision access terminals (remote verification).

Runs on any always-on computer inside the gym (mini PC, front-desk laptop), on the same network as the
Hikvision terminals. Python 3.8+ only, nothing to install.

  Member taps a card, finger or face on the terminal
    -> the terminal sends the event here (HTTP listening, "remote verification" switched on)
    -> this bridge asks GymPulse AI: does this member have an active membership?
    -> it tells the terminal to open (success) or not (failed), with a short reason on the screen

Each member's Employee No. on the terminal must be their GymPulse member code (8 letters/numbers, shown on
their profile), or their card number must be linked to them in GymPulse.

Setup: see door_bridge/README.md. Settings live in bridge_config.json next to this file:
{
  "gympulse_link": "https://<project>.supabase.co/functions/v1/door-access?key=<your device key>",
  "listen_port": 8099,
  "when_offline": "deny",
  "terminals": [
    {"ip": "192.168.1.64", "user": "admin", "password": "<terminal password>", "door": "Main door"},
    {"ip": "192.168.1.65", "user": "admin", "password": "<terminal password>", "door": "Exit"}
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
    """PUT /ISAPI/AccessControl/remoteCheck on the terminal (digest login), with the result."""
    url = f"http://{term['ip']}/ISAPI/AccessControl/remoteCheck?format=json"
    body = json.dumps({"RemoteCheck": {"serialNo": int(serial), "checkResult": "success" if allow else "failed",
                                       "info": (info or "")[:32]}}).encode()
    pm = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    pm.add_password(None, f"http://{term['ip']}/", term.get("user", "admin"), term.get("password", ""))
    opener = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(pm))
    req = urllib.request.Request(url, data=body, method="PUT", headers={"Content-Type": "application/json"})
    try:
        with opener.open(req, timeout=4) as r:
            return r.status < 300
    except Exception as e:
        log.warning("Could not answer terminal %s (%s)", term["ip"], e)
        return False


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
        return next((t for t in CFG["terminals"] if t.get("ip") == ip), None)

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
        if ev:
            threading.Thread(target=handle, args=(term, ev), daemon=True).start()

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
    log.info("GymPulse AI door bridge listening on port %s for %d terminal(s)", port, len(CFG["terminals"]))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
