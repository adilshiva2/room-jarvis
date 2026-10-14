#!/usr/bin/env python3
"""Jarvis Doctor: checks every part of Jarvis, fixes what it can, and keeps a log.

Runs on the Pi as root (a systemd timer calls it every 5 minutes).
Modes:
  check   - one checkup; restart dead pieces; write one line to the log (default)
  report  - print a full status + recent log, ready to paste to Claude
What it can fix by itself: a stopped jarvis service, a stopped Docker container.
Everything else it only reports, so it never makes things worse.
"""
import base64
import json
import pathlib
import subprocess
import sys
import time
import urllib.request

JARVIS_DIR = pathlib.Path("/home/adil/jarvis")
LOG = JARVIS_DIR / "doctor.log"
TOKEN_FILE = JARVIS_DIR / "ha-token.txt"
HA = "http://127.0.0.1:8123"
BOARD = "http://192.168.0.215"
PW_FILE = JARVIS_DIR / "board-password.txt"   # the board's web password, never committed
BOARD_AUTH = base64.b64encode(
    ("jarvis:" + (PW_FILE.read_text().strip() if PW_FILE.exists() else "")).encode()).decode()
CONTAINERS = ["homeassistant", "whisper", "piper"]
ENTITY_MATCH = "jarvis_desk"  # report every Home Assistant entity whose id contains this
LOG_KEEP = 2000  # lines


def sh(cmd: str) -> str:
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r.stdout.strip()


def http(url: str, headers: dict | None = None, timeout: int = 6):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        return None, str(e).encode()


def checkup():
    """Returns (status dict, list of fixes applied)."""
    status, fixes = {}, []

    # 1. The Jarvis server (HUD) service
    if sh("systemctl is-active jarvis") != "active":
        sh("systemctl restart jarvis")
        time.sleep(2)
        fixes.append("restarted jarvis service")
    status["jarvis service"] = sh("systemctl is-active jarvis")

    # 2. Docker containers
    for c in CONTAINERS:
        running = sh(f"docker inspect -f '{{{{.State.Running}}}}' {c} 2>/dev/null")
        if running != "true":
            sh(f"docker start {c}")
            time.sleep(3)
            running = sh(f"docker inspect -f '{{{{.State.Running}}}}' {c} 2>/dev/null")
            fixes.append(f"started container {c}" + ("" if running == "true" else " (FAILED)"))
        status[c] = "up" if running == "true" else "DOWN"

    # 3. Home Assistant answering?
    token = TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else ""
    ha_headers = {"Authorization": f"Bearer {token}"}
    code, _ = http(f"{HA}/api/", ha_headers)
    status["home assistant api"] = "ok" if code == 200 else f"FAIL ({code})"

    # 4. The board answering?
    code, _ = http(f"{BOARD}/", {"Authorization": f"Basic {BOARD_AUTH}"})
    status["board (192.168.0.215)"] = "ok" if code == 200 else f"FAIL ({code})"

    # 5. What Home Assistant thinks of each piece of the room
    if status["home assistant api"] == "ok":
        code, body = http(f"{HA}/api/states", ha_headers, timeout=10)
        if code == 200:
            try:
                found = 0
                for s in json.loads(body):
                    if ENTITY_MATCH in s.get("entity_id", ""):
                        status[s["entity_id"]] = s.get("state", "?")
                        found += 1
                if found == 0:
                    status["room entities"] = f"missing (none match '{ENTITY_MATCH}')"
            except Exception:
                status["room entities"] = "unreadable"
        else:
            status["room entities"] = f"missing ({code})"

    # 6. Pi health
    status["disk free"] = sh("df -h / | awk 'NR==2{print $4}'") or "?"
    raw = sh("cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null")
    if raw.isdigit():
        status["cpu temp"] = f"{int(raw) // 1000} C" + (" HOT" if int(raw) >= 80000 else "")

    return status, fixes


def is_bad(value: str) -> bool:
    v = str(value)
    return "FAIL" in v or "DOWN" in v or "missing" in v or "HOT" in v or v in (
        "unavailable", "unknown", "inactive", "failed", "unreadable")


def write_log(status, fixes):
    problems = [k for k, v in status.items() if is_bad(v)]
    stamp = time.strftime("%Y-%m-%d %H:%M")
    if not problems and not fixes:
        line = f"{stamp} OK"
    else:
        parts = []
        if fixes:
            parts.append("fixed: " + "; ".join(fixes))
        if problems:
            parts.append("bad: " + "; ".join(f"{k}={status[k]}" for k in problems))
        line = f"{stamp} ISSUES  " + "  |  ".join(parts)
    lines = LOG.read_text().splitlines() if LOG.exists() else []
    lines.append(line)
    LOG.write_text("\n".join(lines[-LOG_KEEP:]) + "\n")
    return line


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    status, fixes = checkup()
    line = write_log(status, fixes)
    if mode == "report":
        print("=== Jarvis Doctor report ===")
        print("Now:")
        for k, v in status.items():
            flag = "  <-- problem" if is_bad(v) else ""
            print(f"  {k}: {v}{flag}")
        if fixes:
            print("Fixes just applied: " + "; ".join(fixes))
        print("\nRecent history (last 25 checkups):")
        lines = LOG.read_text().splitlines() if LOG.exists() else []
        for l in lines[-25:]:
            print("  " + l)
    else:
        print(line)


if __name__ == "__main__":
    main()
