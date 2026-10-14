#!/usr/bin/env python3
"""Jarvis server - sits between the HUD and the board.

The HUD (phone / Mac browser) talks to THIS program.
This program talks to the board with the board's password.
Nobody on the WiFi can use the HUD without the HUD PIN.

Run it from the ~/jarvis folder:   python3 jarvis-server.py
"""
import base64
import http.server
import json
import os
import secrets
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# ---------- EDIT THESE THREE LINES ----------
NODE_IP = "192.168.0.215"       # the board
NODE_USER = "jarvis"            # same as web_server auth username in the YAML
NODE_PASS = ""                  # board web password; read from board-password.txt below
_pw_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "board-password.txt")
if os.path.exists(_pw_file):
    NODE_PASS = open(_pw_file).read().strip()
else:
    sys.exit("Missing board-password.txt next to this file (the board's web password).")
HUD_PIN = "3000"                # what the HUD asks you for (change it if you like)
# --------------------------------------------

PORT = 8000
HERE = os.path.dirname(os.path.abspath(__file__))
HUD_FILE = os.path.join(HERE, "jarvis-hud.html")
TOKENS = set()          # signed-in HUDs (forgotten when the server stops)
BAD_PIN_AT = [0.0]      # last wrong PIN time (slows guessing)
STATE = {}              # latest state of each thing on the board, by id
LAST_SEEN = [0.0]       # when the board last said anything
BOARD_ERR = [""]        # last problem talking to the board


def node(path, method="GET"):
    """Ask the board for something, with its password."""
    cred = base64.b64encode(f"{NODE_USER}:{NODE_PASS}".encode()).decode()
    req = urllib.request.Request(
        f"http://{NODE_IP}{path}", method=method,
        headers={"Authorization": "Basic " + cred},
    )
    with urllib.request.urlopen(req, timeout=4) as r:
        body = r.read().decode("utf-8", "replace")
        return r.status, body


def listen_to_board():
    """One quiet connection to the board. It pushes every change to us.

    This is much gentler on the board than asking it questions over and over.
    """
    cred = base64.b64encode(f"{NODE_USER}:{NODE_PASS}".encode()).decode()
    while True:
        try:
            req = urllib.request.Request(
                f"http://{NODE_IP}/events",
                headers={"Authorization": "Basic " + cred, "Accept": "text/event-stream"},
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                BOARD_ERR[0] = ""
                print("board: connected", flush=True)
                event = None
                for raw in r:
                    line = raw.decode("utf-8", "replace").rstrip("\r\n")
                    LAST_SEEN[0] = time.time()
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:"):
                        if event == "state":
                            try:
                                obj = json.loads(line[5:].strip())
                                if "id" in obj:
                                    STATE[obj["id"]] = obj
                            except ValueError:
                                pass
                    elif line == "":
                        event = None
        except urllib.error.HTTPError as e:
            BOARD_ERR[0] = "board said %s (password wrong?)" % e.code
        except Exception as e:
            BOARD_ERR[0] = str(e)
        print("board: not connected (%s), retrying in 5 s" % BOARD_ERR[0], flush=True)
        time.sleep(5)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # one short line per request (skip the 2-second status checks)
        if "/api/state" in (fmt % args):
            return
        sys.stdout.write("%s %s\n" % (self.address_string(), fmt % args))

    # ----- helpers -----
    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def ok_json(self, obj):
        self.send(200, json.dumps(obj))

    def signed_in(self):
        tok = self.headers.get("X-Jarvis-Token", "")
        if tok and tok in TOKENS:
            return True
        self.send(401, '{"error":"sign in"}')
        return False

    # ----- GET -----
    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        if url.path in ("/", "/jarvis-hud.html", "/index.html"):
            try:
                with open(HUD_FILE, "rb") as f:
                    self.send(200, f.read(), "text/html; charset=utf-8")
            except OSError:
                self.send(404, "jarvis-hud.html not found next to jarvis-server.py", "text/plain")
            return
        if url.path == "/api/state":
            if not self.signed_in():
                return
            up = time.time() - LAST_SEEN[0] < 90
            out = {
                "light": STATE.get("light-desk_strip"),
                "temp": STATE.get("sensor-room_temperature"),
                "hum": STATE.get("sensor-room_humidity"),
                "auto_wake": STATE.get("switch-auto_wake"),
                "up": up,
                "error": BOARD_ERR[0],
            }
            self.ok_json(out)
            return
        self.send(404, '{"error":"not found"}')

    # ----- POST -----
    def do_POST(self):
        url = urllib.parse.urlsplit(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        if url.path == "/api/login":
            try:
                pin = json.loads(raw or b"{}").get("pin", "")
            except ValueError:
                pin = ""
            if time.time() - BAD_PIN_AT[0] < 1.0:
                time.sleep(1.0)
            if secrets.compare_digest(str(pin), HUD_PIN):
                tok = secrets.token_urlsafe(24)
                TOKENS.add(tok)
                self.ok_json({"token": tok})
            else:
                BAD_PIN_AT[0] = time.time()
                self.send(403, '{"error":"wrong PIN"}')
            return
        if url.path == "/api/logout":
            TOKENS.discard(self.headers.get("X-Jarvis-Token", ""))
            self.ok_json({"ok": True})
            return
        if url.path.startswith("/api/node/"):
            if not self.signed_in():
                return
            path = url.path[len("/api/node"):]
            if url.query:
                path += "?" + url.query
            try:
                code, body = node(path, "POST")
                self.send(code, body or "{}")
            except urllib.error.HTTPError as e:
                self.send(e.code, json.dumps({"error": "board said %s" % e.code}))
            except Exception as e:
                self.send(502, json.dumps({"error": str(e)}))
            return
        self.send(404, '{"error":"not found"}')


def my_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    threading.Thread(target=listen_to_board, daemon=True).start()
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("Jarvis server running.")
    print("  On this Mac:   http://localhost:%d" % PORT)
    print("  On your phone: http://%s:%d" % (my_ip(), PORT))
    print("Press Ctrl+C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
