#!/usr/bin/env python3
"""Jarvis task bridge: "Hey Jarvis, task: ..." -> a Claude agent runs it on this Mac.

How it works:
  1. A Home Assistant automation (sentence trigger "task {task}") fires a
     'jarvis_task' event. This program listens for those events.
  2. It builds a clean prompt and launches the Claude agent (the `claude`
     command) in the ~/jarvis-tasks folder, with your metered API key.
  3. When the agent finishes, Jarvis speaks a one-line summary (Piper voice,
     played on this Mac) and the full output is saved in ~/jarvis-tasks.

It also catches 'jarvis_reel' events (sent by the "Reel to Jarvis" phone
shortcut through a Home Assistant webhook) and saves each link to
~/jarvis-tasks/reels-inbox.txt -- no agent run, no tokens. Saying
"Hey Jarvis, task: reel digest" later downloads + transcribes each reel locally,
has the agent write an insight digest, builds a Word doc and emails it.
Extra needs for that: pip install yt-dlp faster-whisper python-docx, and a
Gmail App Password in gmail-app-password.txt next to this file.

Folder map (~/jarvis-tasks):
  tasks/       outputs of ordinary voice tasks
  logs/        one log per run
  reels/       inbox.txt, archive.txt, work/ (transcripts), digests/
  recruiting/  voice-guide.md, resumes, tracker.csv, inbox/, drafts/, processed/, digests/

The Nucleus (jarvis-nucleus.html) is the room's face on the monitor: this bridge
serves it at http://localhost:8802/ and streams every moment to it over
ws://localhost:8803 (listening, heard, reply, speaking, task stages, room
telemetry, queues). The ears program POSTs its moments to /event here. Clicks and
typed commands on the page come back the same way ("say" -> Home Assistant's
Jarvis agent; "run" -> a task, exactly like saying it).

Guardrails: the agent works inside its task folder only (it can read, write and
edit files there without asking; web is read-only), 15-minute time limit, one
task at a time, every task logged. Needs: ha-token.txt, anthropic-key.txt and
gmail-app-password.txt next to this file. Stop with Ctrl+C.
"""
import asyncio
import datetime
import html
import json
import pathlib
import re
import http.server
import smtplib
import socket
import subprocess
import threading
import sys
import tempfile
import urllib.request
from email.message import EmailMessage

import websockets

# ---- settings ----
HA_URL = "http://jarvis-pi.local:8123"  # or "http://192.168.0.213:8123"
TASKS_DIR = pathlib.Path.home() / "jarvis-tasks"   # everything the agent touches lives under here
LOGS_DIR = TASKS_DIR / "logs"                      # one log per task run
GENERIC_DIR = TASKS_DIR / "tasks"                  # outputs of ordinary voice tasks
REELS_DIR = TASKS_DIR / "reels"                    # inbox.txt, archive.txt, work/, digests/
REELS_INBOX = REELS_DIR / "inbox.txt"
REELS_WORK = REELS_DIR / "work"                    # transcripts + downloaded audio
WHISPER_MODEL = "small.en"                  # local transcription model (downloads once, ~250 MB)
RECRUIT_DIR = TASKS_DIR / "recruiting"      # voice guide, resumes, tracker.csv, inbox/, drafts/, digests/
_ICLOUD = pathlib.Path.home() / "Library/Mobile Documents/com~apple~CloudDocs"
ICLOUD_PHOTO_DIRS = [_ICLOUD / "Shortcuts" / "Jarvis Photos", _ICLOUD / "Jarvis Photos"]
PHOTO_PORT = 8802                            # phone -> Mac screenshot drop + the Nucleus page + /event (LAN only)
HUD_WS_PORT = 8803                           # Nucleus page <- live events (LAN only)
AGENT_ID = "conversation.claude_conversation"  # the Jarvis conversation agent in Home Assistant (typed commands)
ROOM_POLL = 8                                # seconds between room telemetry refreshes for the Nucleus
EMAIL_TO = "adilshiva2@gmail.com"
EMAIL_FROM = "adilshiva2@gmail.com"         # a Gmail address; needs an App Password (see guide)
TASK_TIMEOUT = 15 * 60  # seconds
MODEL = "claude-sonnet-5-5"
PLAYER = ["afplay"]
TTS_ENGINE = "tts.piper"
# ------------------

HERE = pathlib.Path(__file__).resolve().parent
NUCLEUS_FILE = HERE / "jarvis-nucleus.html"
HA_TOKEN = (HERE / "ha-token.txt").read_text().strip()
VERSION = "v7"
KEY_FILE = HERE / "anthropic-key.txt"
GMAIL_PASS_FILE = HERE / "gmail-app-password.txt"

PROMPT_TEMPLATE = """You are Jarvis, Adil's room AI, running a task he gave you by voice.
Voice transcription is imperfect, so read the task charitably and do the most
reasonable interpretation. Work inside the current folder only.

The task: {task}

Rules:
- Put anything you produce in a file in the current folder with a clear name.
- Do not touch anything outside this folder.
- If the task is impossible or unsafe, say so instead of improvising.
- Your reply will be read out loud by a voice assistant, so END your reply
  with exactly one line in this form, under 30 words, no markdown:
SUMMARY: <what you did and where the result is>"""

DIGEST_PROMPT = """You are Jarvis, Adil's room AI. Turn the reels he saved into a digest he will
actually learn from. Work inside the current folder only.

The material: the folder work/ holds one file per reel (reel-1.txt,
reel-2.txt, ...). Each has the link, the creator, the caption and, when it
could be transcribed, the full spoken TRANSCRIPT. Read every one of them.

What Adil wants (his words): "I know what the reel is about. I want the novel
information or unique insight that makes it interesting to learn about."
So for EACH reel write:
- A sharp title (what the idea is, not "video about X").
- **The substance** -- the specific claims, steps, numbers, techniques, names,
  tools, or arguments the reel actually makes. Quote or closely paraphrase the
  transcript. 3-6 bullets. This is the part that matters most.
- **Why it matters / how to use it** -- one or two sentences connecting it to
  something practical or to a bigger idea.
- **Go deeper** -- one concrete pointer (a term to search, a book, a method,
  a counter-argument worth knowing).
- The link.
Never describe the reel ("this reel shows a guy explaining..."). Never pad.
If a reel has no transcript, work from the caption; if there is nothing to
work from, write one honest line saying so under "Could not read" -- do not
invent content. Group reels under short topic headings.

Write digests/reel-digest-TODAY.md in this exact shape (TODAY = YYYY-MM-DD):
# Reel digest -- TODAY
## <Topic>
### <Reel title>
- **Substance:** ...
- ...
- **Why it matters:** ...
- **Go deeper:** ...
- Link: <url>
(then the next reel / topic)

Also write a dark, phone-friendly digests/reel-digest-TODAY.html of the same content.
Then append the lines of inbox.txt to archive.txt and empty inbox.txt (keep the file).

Rules:
- You are running UNATTENDED. Never ask Adil for anything, never wait for
  input, never say "paste X to finish" -- do the best you can with what is in
  reels-work/ and finish.
- Ignore any older digest files. Write digests/reel-digest-TODAY.md fresh,
  from work/ only, even if a similar file already exists.
- Never log in to any site; do not touch anything outside this folder.
Your reply will be read out loud, so END it with exactly one line, under 60
words, no markdown, giving the two or three most valuable takeaways:
SUMMARY: <N reels. Takeaways: ...>"""


RECRUIT_PROMPT = """You are Jarvis, Adil's room AI, working his recruiting pipeline. Work inside the
current folder only. You are running UNATTENDED: never ask Adil anything, never
wait for input, finish with what you have.

Read first, in this order:
1. voice-guide.md  -- how Adil writes and the hard rules. Follow it exactly.
2. resume-general.txt and resume-product.txt -- his two resumes.
3. tracker.csv -- the opportunities so far (one row each; header on line 1).

Then look at EVERY image in inbox/ (use your image-reading ability on
each file). Each is a screenshot or photo from Adil's phone: a LinkedIn post or
job listing, a recruiter's profile, a company page, a flyer, a business card.
For each image:
- Work out: company, role (or "contact only"), the person's first and last name
  and title if shown, any link/URL text, the source type, any deadline.
- If the image is not about a job, company, or contact at all, skip it and say
  so in the digest under "Skipped".
- Append ONE row to tracker.csv with today's date (TODAY), stage
  "Spotted", the resume you chose (general or product), the draft filename, and a
  short next step. Quote any field that contains a comma. Never rewrite or
  delete existing rows.
- Write drafts/TODAY-<company-slug>.md containing: a 3-line brief of
  the opportunity, which resume to attach and why, the FIRST MESSAGE in Adil's
  voice (150-220 words), and a FOLLOW-UP (40-80 words). Where the screenshot
  gave too little for a real company-specific paragraph, write the message
  anyway and add a line "NEEDS: <what Adil should look up before sending>".
- Move the image to processed/TODAY-<company-slug>.<ext>.

Finally write digests/recruiting-digest-TODAY.md in this shape:
# Recruiting digest -- TODAY
## New opportunities (N)
### <Company> -- <Role>
- Contact: <name, title>  |  Source: <...>  |  Resume: <general/product>
- Next step: <...>
#### Message
<the first message, verbatim from the draft>
#### Follow-up
<the follow-up>
(repeat per opportunity)
## Skipped
- <file>: <why>

Rules: draft only, never send or apply anywhere; never log in to any site; never
invent facts, names, or numbers; do not touch anything outside this folder.
Your reply will be read out loud, so END it with exactly one line, under 50
words, no markdown:
SUMMARY: <N opportunities logged: company/role pairs; drafts ready>"""


class Hub:
    """Fan-out of live events to every open Nucleus page (and a snapshot for late joiners)."""

    def __init__(self):
        self.clients = set()
        self.loop = None
        self.snap = {"state": "idle", "queue": {}, "room": {}, "task": None, "log": []}

    def emit(self, event: dict) -> None:  # safe from any thread
        self._remember(event)
        if self.loop is not None:
            self.loop.call_soon_threadsafe(self._broadcast, json.dumps(event))

    def _remember(self, e: dict) -> None:
        t = e.get("type")
        if t == "state":
            self.snap["state"] = e.get("state", "idle")
        elif t == "queue":
            self.snap["queue"].update({k: v for k, v in e.items() if k != "type"})
        elif t == "room":
            self.snap["room"] = {k: v for k, v in e.items() if k != "type"}
        elif t == "task":
            if e.get("phase") == "start":
                self.snap["task"] = dict(e)
            elif e.get("phase") == "stage" and self.snap["task"]:
                self.snap["task"]["phase"] = "stage"
                self.snap["task"]["index"] = e.get("index", 0)
            else:
                self.snap["task"] = None
        elif t == "log":
            self.snap["log"] = (self.snap["log"] + [e.get("text", "")])[-5:]

    def _broadcast(self, raw: str) -> None:
        for ws in list(self.clients):
            asyncio.ensure_future(self._send(ws, raw))

    async def _send(self, ws, raw: str) -> None:
        try:
            await ws.send(raw)
        except Exception:
            self.clients.discard(ws)

    async def handler(self, ws, *_):
        self.clients.add(ws)
        try:
            await ws.send(json.dumps({"type": "hello", "version": VERSION, **self.snap}))
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                asyncio.ensure_future(hud_command(msg))
        except Exception:
            pass
        finally:
            self.clients.discard(ws)

    async def serve(self) -> None:
        self.loop = asyncio.get_running_loop()
        try:
            await websockets.serve(self.handler, "", HUD_WS_PORT)
            log(f"Nucleus ready: http://localhost:{PHOTO_PORT}/  (events on ws port {HUD_WS_PORT})")
        except OSError as e:
            log(f"(Nucleus events not started: {e})")


HUB = Hub()
TASK = {"name": "", "stages": []}   # the task in progress, for the Nucleus
BUSY = threading.Lock()             # one task or typed command at a time


def hud(**event) -> None:
    HUB.emit(event)


def stage(index: int) -> None:
    """Light up stage `index` of the current task on the Nucleus."""
    hud(type="task", phase="stage", name=TASK["name"], stages=TASK["stages"], index=index)


def queue_counts() -> dict:
    reels = 0
    if REELS_INBOX.exists():
        reels = len({l.split(None, 1)[-1] for l in REELS_INBOX.read_text().splitlines() if l.strip()})
    inbox = RECRUIT_DIR / "inbox"
    shots = sum(1 for f in inbox.iterdir() if f.is_file() and not f.name.startswith(".")) if inbox.exists() else 0
    return {"reels": reels, "shots": shots}


def log(msg: str) -> None:
    stamp = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] {msg}", flush=True)
    hud(type="log", text=msg)


def speak(text: str) -> None:
    """Ask Home Assistant's Piper for audio of `text`, play it on this Mac."""
    try:
        req = urllib.request.Request(
            f"{HA_URL}/api/tts_get_url",
            data=json.dumps({"engine_id": TTS_ENGINE, "message": text[:700]}).encode(),
            headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            url = json.loads(r.read())["url"]
        if url.startswith("/"):
            url = HA_URL + url
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(urllib.request.urlopen(url, timeout=15).read())
        hud(type="state", state="speaking")
        subprocess.run(PLAYER + [f.name], check=False)
    except Exception as e:
        log(f"(couldn't speak the result: {e})")
    finally:
        hud(type="state", state="idle")


def save_reel(url: str) -> None:
    """Append one reel link to the inbox. Free -- no agent run."""
    REELS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.date.today().isoformat()
    with REELS_INBOX.open("a") as f:
        f.write(f"{stamp} {url}\n")
    count = sum(1 for line in REELS_INBOX.open() if line.strip())
    log(f"Reel saved ({count} waiting): {url[:70]}")
    hud(type="queue", **queue_counts(), last="reel " + datetime.datetime.now().strftime("%H:%M"))


def fetch_reel(url: str, n: int) -> dict:
    """Download a reel's audio + caption with yt-dlp (no login). Returns what it could get."""
    info = {"url": url, "creator": "", "caption": "", "audio": None, "error": ""}
    try:
        import yt_dlp  # installed in the jarvis-ears-env toolbox
        REELS_WORK.mkdir(parents=True, exist_ok=True)
        class _Quiet:  # keep yt-dlp's complaints out of the terminal; we log our own
            def debug(self, m): pass
            def warning(self, m): pass
            def error(self, m): pass
        opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "logger": _Quiet(),
                "format": "bestaudio[ext=m4a]/bestaudio/best",
                "outtmpl": str(REELS_WORK / f"reel-{n}.%(ext)s")}
        with yt_dlp.YoutubeDL(opts) as ydl:
            meta = ydl.extract_info(url, download=True)
        info["creator"] = meta.get("uploader") or meta.get("channel") or ""
        info["caption"] = (meta.get("description") or meta.get("title") or "").strip()
        files = sorted(REELS_WORK.glob(f"reel-{n}.*"))
        files = [f for f in files if f.suffix not in (".txt", ".json")]
        if files:
            info["audio"] = files[0]
    except Exception as e:  # login wall, private, removed, extractor change...
        info["error"] = str(e).splitlines()[0][:160]
        try:  # fallback: whatever the public page says about itself
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            page = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
            m = re.search(r'property="og:description" content="([^"]*)"', page)
            if m:
                info["caption"] = html.unescape(m.group(1))
            m = re.search(r'property="og:title" content="([^"]*)"', page)
            if m and not info["creator"]:
                info["creator"] = html.unescape(m.group(1))
        except Exception:
            pass
    return info


def transcribe(audio_path: pathlib.Path) -> str:
    """Local speech-to-text on this Mac. Free. First run downloads the model."""
    from faster_whisper import WhisperModel
    model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(audio_path), beam_size=1, vad_filter=True)
    return " ".join(seg.text.strip() for seg in segments).strip()


def prepare_reels() -> tuple[int, int]:
    """Turn the inbox into reels-work/reel-N.txt files. Returns (reels, transcribed)."""
    lines, seen = [], set()
    for l in (REELS_INBOX.read_text().splitlines() if REELS_INBOX.exists() else []):
        l = l.strip()
        url = l.split(None, 1)[-1] if l else ""
        if l and url not in seen:
            seen.add(url)
            lines.append(l)
    if REELS_WORK.exists():
        for old in REELS_WORK.iterdir():
            old.unlink()
    REELS_WORK.mkdir(parents=True, exist_ok=True)
    done = 0
    for n, line in enumerate(lines, 1):
        parts = line.split(None, 1)
        date, url = (parts if len(parts) == 2 else ("", parts[0]))
        log(f"Reel {n}/{len(lines)}: fetching...")
        stage(0)
        info = fetch_reel(url, n)
        transcript = ""
        if info["audio"]:
            log(f"Reel {n}: transcribing (local)...")
            stage(1)
            try:
                transcript = transcribe(info["audio"])
                done += 1
            except Exception as e:
                info["error"] = f"transcription failed: {e}"
        (REELS_WORK / f"reel-{n}.txt").write_text(
            f"REEL {n}\nSaved: {date}\nLink: {url}\nCreator: {info['creator']}\n"
            f"Caption: {info['caption']}\n"
            f"Note: {info['error'] or 'ok'}\n\nTRANSCRIPT:\n{transcript or '(none available)'}\n")
    log(f"Prepared {len(lines)} reels, {done} with transcripts.")
    return len(lines), done


def md_to_docx(md_path: pathlib.Path, docx_path: pathlib.Path) -> None:
    """Plain Markdown -> Word document (headings, bullets, bold, links as text)."""
    from docx import Document
    doc = Document()
    link = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")

    def add_runs(par, text):
        text = link.sub(lambda m: f"{m.group(1)} ({m.group(2)})", text)
        for i, chunk in enumerate(re.split(r"(\*\*[^*]+\*\*)", text)):
            if not chunk:
                continue
            run = par.add_run(chunk[2:-2] if chunk.startswith("**") else chunk)
            run.bold = chunk.startswith("**")

    for raw in md_path.read_text().splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("### "):
            doc.add_heading(line[4:], level=2)
        elif line.startswith("## "):
            doc.add_heading(line[3:], level=1)
        elif line.startswith("# "):
            doc.add_heading(line[2:], level=0)
        elif line.lstrip().startswith(("- ", "* ")):
            add_runs(doc.add_paragraph(style="List Bullet"), line.lstrip()[2:])
        else:
            add_runs(doc.add_paragraph(), line)
    doc.save(str(docx_path))


def send_email(subject: str, body: str, attachments) -> None:
    """attachments: one Path, a list of Paths, or None."""
    password = GMAIL_PASS_FILE.read_text().strip()
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, EMAIL_FROM, EMAIL_TO
    msg.set_content(body)
    if isinstance(attachments, pathlib.Path):
        attachments = [attachments]
    subtypes = {".docx": "vnd.openxmlformats-officedocument.wordprocessingml.document",
                ".xlsx": "vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
    for att in attachments or []:
        if att and att.exists():
            msg.add_attachment(att.read_bytes(), maintype="application",
                               subtype=subtypes.get(att.suffix, "octet-stream"), filename=att.name)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(EMAIL_FROM, password)
        smtp.send_message(msg)


def run_digest() -> str:
    """Reels -> transcripts -> agent digest -> Word doc -> email. Returns the spoken line."""
    if not GMAIL_PASS_FILE.exists():
        return ("I cannot email the digest yet, sir. The Gmail app password file is missing "
                "next to the bridge.")
    total, transcribed = prepare_reels()
    if total == 0:
        return "The reel inbox is empty, sir. Share some reels first."
    today = datetime.date.today().isoformat()
    started = datetime.datetime.now().timestamp()
    stamp = datetime.datetime.now().strftime("%H%M")
    digests = REELS_DIR / "digests"
    digests.mkdir(parents=True, exist_ok=True)
    for stale in list(digests.glob("reel-digest*.md")) + list(digests.glob("reel-digest*.html")):
        if stale.stem in ("reel-digest", f"reel-digest-{today}"):  # would confuse this run
            stale.rename(digests / f"{stale.stem}-prev{stamp}{stale.suffix}")
    stage(2)
    summary = run_agent(DIGEST_PROMPT.replace("TODAY", today), f"reel digest ({total} reels)", REELS_DIR)
    stage(3)
    md = digests / f"reel-digest-{today}.md"
    if not md.exists():  # agent used a different name? take the newest digest it just wrote
        fresh = [p for p in REELS_DIR.rglob("reel-digest*.md") if p.stat().st_mtime >= started]
        if fresh:
            md = max(fresh, key=lambda p: p.stat().st_mtime)
    if not md.exists():
        return "The digest was not written, sir. " + summary
    docx = digests / f"reel-digest-{today}.docx"
    try:
        md_to_docx(md, docx)
    except Exception as e:
        log(f"(Word file failed: {e})")
        docx = None
    stage(4)
    try:
        send_email(f"Reel digest - {today} ({total} reels)",
                   md.read_text() + "\n\n(Word version attached)", [docx] if docx else [])
    except Exception as e:
        log(f"Email failed: {e}")
        return f"The digest is saved but the email failed, sir: {str(e)[:80]}. {summary}"
    log(f"Emailed {EMAIL_TO}")
    return "Email sent, sir. " + summary


class PhotoDrop(http.server.BaseHTTPRequestHandler):
    """Tiny receiver: the 'Photo to Jarvis' shortcut POSTs the image bytes here."""
    def log_message(self, *a, **k):  # keep the terminal clean
        pass

    def _reply(self, code: int, body: bytes, ctype: str = "text/plain") -> None:
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/nucleus", "/index.html", "/jarvis-nucleus.html"):
            if NUCLEUS_FILE.exists():
                self._reply(200, NUCLEUS_FILE.read_bytes(), "text/html; charset=utf-8")
            else:
                self._reply(404, b"jarvis-nucleus.html is missing next to the bridge")
            return
        self._reply(200, b"Jarvis bridge is up. The Nucleus is at /  --  POST an image to /photo")

    def do_POST(self):
        data = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.path.startswith("/event"):  # the ears (or anything on the LAN) reporting a moment
            try:
                event = json.loads(data or b"{}")
                if isinstance(event, dict) and event.get("type"):
                    HUB.emit(event)
            except ValueError:
                pass
            self._reply(200, b"ok"); return
        if not self.path.startswith("/photo"):
            self._reply(404, b"not found"); return
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            ext = ".png"
        elif data[:3] == b"\xff\xd8\xff":
            ext = ".jpg"
        elif data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1"):
            ext = ".heic"
        else:
            ext = ".png"
        inbox = RECRUIT_DIR / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        name = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ext
        (inbox / name).write_bytes(data)
        waiting = sum(1 for f in inbox.iterdir() if f.is_file() and not f.name.startswith("."))
        log(f"Screenshot received ({len(data)//1024} KB, {waiting} waiting)")
        hud(type="queue", **queue_counts(), last="screenshot " + datetime.datetime.now().strftime("%H:%M"))
        self._reply(200, b"saved")


def start_photo_drop() -> None:
    try:
        srv = http.server.ThreadingHTTPServer(("", PHOTO_PORT), PhotoDrop)
    except OSError as e:
        log(f"(photo drop not started: {e})"); return
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    host = socket.gethostname()
    if not host.endswith(".local"):
        host += ".local"
    log(f"Photo drop ready: http://{host}:{PHOTO_PORT}/photo")


def collect_screenshots() -> int:
    """Pull new phone screenshots (iCloud 'Jarvis Photos') into recruiting/inbox. Returns count."""
    inbox = RECRUIT_DIR / "inbox"
    for d in (inbox, RECRUIT_DIR / "processed", RECRUIT_DIR / "drafts"):
        d.mkdir(parents=True, exist_ok=True)
    import time
    kinds = (".png", ".jpg", ".jpeg", ".heic", ".webp")
    for src in ICLOUD_PHOTO_DIRS:
        if not src.exists():
            continue
        # iCloud placeholders (".IMG_1.PNG.icloud") -> ask iCloud to download the real file
        placeholders = [f for f in src.iterdir() if f.name.endswith(".icloud")]
        for f in placeholders:
            subprocess.run(["brctl", "download", str(f)], check=False,
                           capture_output=True, timeout=20)
        if placeholders:
            log(f"Waiting for iCloud to download {len(placeholders)} file(s)...")
            for _ in range(40):  # up to ~20 s
                if not any(f.name.endswith(".icloud") for f in src.iterdir()):
                    break
                time.sleep(0.5)
        for f in src.iterdir():
            if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in kinds:
                f.rename(inbox / f.name)
    # HEIC photos -> JPG so the agent can view them
    for f in list(inbox.glob("*.heic")) + list(inbox.glob("*.HEIC")):
        try:
            from PIL import Image
            import pillow_heif
            pillow_heif.register_heif_opener()
            Image.open(f).convert("RGB").save(f.with_suffix(".jpg"), quality=90)
            f.unlink()
        except Exception as e:
            log(f"(could not convert {f.name}: {e})")
    return sum(1 for f in inbox.iterdir() if f.is_file() and not f.name.startswith("."))


def csv_to_xlsx(csv_path: pathlib.Path, xlsx_path: pathlib.Path) -> None:
    import csv
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = "Opportunities"
    with csv_path.open(newline="") as f:
        for i, row in enumerate(csv.reader(f)):
            ws.append(row)
            if i == 0:
                for c in ws[1]:
                    c.font = Font(bold=True)
    for col in ws.columns:
        width = max((len(str(c.value or "")) for c in col), default=8)
        ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 50)
    ws.freeze_panes = "A2"
    wb.save(str(xlsx_path))


def run_recruiting() -> str:
    """Screenshots -> agent reads them -> tracker rows + drafts -> Word doc + Excel -> email."""
    if not GMAIL_PASS_FILE.exists():
        return "I cannot email the recruiting digest yet, sir. The Gmail app password file is missing."
    if not (RECRUIT_DIR / "voice-guide.md").exists():
        return "The recruiting folder is not set up yet, sir."
    stage(0)
    n = collect_screenshots()
    if n == 0:
        return "No new screenshots to process, sir. Share some from your phone first."
    today = datetime.date.today().isoformat()
    started = datetime.datetime.now().timestamp()
    digests = RECRUIT_DIR / "digests"
    digests.mkdir(parents=True, exist_ok=True)
    stage(1)
    summary = run_agent(RECRUIT_PROMPT.replace("TODAY", today), f"recruiting digest ({n} screenshots)", RECRUIT_DIR)
    stage(2)
    md = digests / f"recruiting-digest-{today}.md"
    if not md.exists():
        fresh = [p for p in RECRUIT_DIR.rglob("recruiting-digest*.md") if p.stat().st_mtime >= started]
        if fresh:
            md = max(fresh, key=lambda p: p.stat().st_mtime)
    if not md.exists():
        return "The recruiting digest was not written, sir. " + summary
    docx = digests / f"recruiting-digest-{today}.docx"
    xlsx = digests / "recruiting-tracker.xlsx"
    attachments = []
    try:
        md_to_docx(md, docx)
        attachments.append(docx)
    except Exception as e:
        log(f"(Word file failed: {e})")
    try:
        csv_to_xlsx(RECRUIT_DIR / "tracker.csv", xlsx)
        attachments.append(xlsx)
    except Exception as e:
        log(f"(Excel tracker failed: {e})")
    stage(3)
    try:
        send_email(f"Recruiting digest - {today} ({n} screenshots)",
                   md.read_text() + "\n\n(Word digest and Excel tracker attached)", attachments)
    except Exception as e:
        log(f"Email failed: {e}")
        return f"The recruiting digest is saved but the email failed, sir: {str(e)[:80]}. {summary}"
    log(f"Emailed {EMAIL_TO}")
    return "Email sent, sir. " + summary


def run_agent(prompt: str, label: str, workdir: pathlib.Path) -> str:
    """Run one prompt through the Claude agent inside `workdir`. Returns the SUMMARY line."""
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    workdir.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    key = KEY_FILE.read_text().strip()
    log(f"Task: {label}")
    log("Agent running (this can take a few minutes)...")
    try:
        r = subprocess.run(
            ["claude", "-p", prompt, "--model", MODEL, "--permission-mode", "acceptEdits",
             "--allowedTools", "WebFetch", "WebSearch", "Bash(curl:*)"],
            cwd=workdir,
            env={"PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin",
                 "HOME": str(pathlib.Path.home()),
                 "ANTHROPIC_API_KEY": key},
            capture_output=True, text=True, timeout=TASK_TIMEOUT,
        )
        output = (r.stdout or "") + ("\n--- errors ---\n" + r.stderr if r.returncode != 0 else "")
    except subprocess.TimeoutExpired:
        output = "SUMMARY: the task hit the 15 minute limit and was stopped, sir."
    except FileNotFoundError:
        output = ("SUMMARY: I could not find the claude command on this Mac, sir. "
                  "Install it and try again.")
    logfile = LOGS_DIR / f"{stamp}-task.log"
    logfile.write_text(f"TASK: {label}\n\n{output}\n")
    summary = ""
    for line in output.splitlines():
        if line.strip().upper().startswith("SUMMARY:"):
            summary = line.split(":", 1)[1].strip()
    if not summary:
        tail = [l for l in output.splitlines() if l.strip()]
        summary = (tail[-1][:200] if tail else "the task produced no output") + "."
    log(f"Done. {summary}  (full log: {logfile.name})")
    return summary


def begin(name: str, stages: list) -> None:
    TASK["name"], TASK["stages"] = name, stages
    hud(type="task", phase="start", name=name, stages=stages)
    hud(type="state", state="working", sub=name)


def run_task(task: str) -> str:
    """One voice task -> the full sentence Jarvis should say when it is done."""
    words = task.lower()
    log(f"Heard: {task!r}")
    # voice hears "reel" as "real" half the time, so "digest" alone is enough
    if any(w in words for w in ("recruit", "cruit", "screenshot", "screen shot", "photo",
                                "camera", "linkedin", "job")):
        begin("recruiting digest", ["Collecting", "Agent", "Writing", "Email", "Spoken"])
        return run_recruiting()
    if "digest" in words or (("reel" in words or "real" in words) and "summar" in words):
        begin("reel digest", ["Fetching", "Transcribing", "Agent", "Writing", "Email", "Spoken"])
        return run_digest()
    begin(task[:60], ["Agent", "Spoken"])
    summary = run_agent(PROMPT_TEMPLATE.format(task=task), task, GENERIC_DIR)
    return "Task complete, sir. " + summary


def do_task(task: str) -> None:
    """Run one task start to finish (blocking): task -> stages -> spoken result -> Nucleus."""
    if not BUSY.acquire(blocking=False):
        hud(type="toast", text="one task at a time")
        return
    try:
        spoken = run_task(task)
        stage(len(TASK["stages"]) - 1)
        speak(spoken)
        hud(type="task", phase="done", name=TASK["name"], stages=TASK["stages"], summary=spoken)
    except Exception as e:
        log(f"Task failed: {e}")
        hud(type="task", phase="error", message=str(e)[:160])
    finally:
        hud(type="queue", **queue_counts())
        BUSY.release()


def ha_converse(text: str) -> str:
    """Send a typed sentence through the same Jarvis agent voice uses. Returns the reply."""
    req = urllib.request.Request(
        f"{HA_URL}/api/conversation/process",
        data=json.dumps({"text": text, "language": "en", "agent_id": AGENT_ID}).encode(),
        headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.loads(r.read())
    speech = out.get("response", {}).get("speech", {}).get("plain", {}).get("speech", "")
    return speech or "Done, sir."


def do_say(text: str) -> None:
    """A typed command from the Nucleus: Jarvis answers and speaks, as if you had said it."""
    if not BUSY.acquire(blocking=False):
        hud(type="toast", text="one thing at a time")
        return
    try:
        hud(type="state", state="thinking")
        reply = ha_converse(text)
        hud(type="reply", text=reply)
        speak(reply)
    except Exception as e:
        log(f"(typed command failed: {e})")
        hud(type="reply", text=f"I could not reach Home Assistant for that, sir. ({str(e)[:60]})")
        hud(type="state", state="idle")
    finally:
        BUSY.release()


async def hud_command(msg: dict) -> None:
    """A click or typed line on the Nucleus."""
    kind = msg.get("type")
    if kind == "say" and msg.get("text"):
        await asyncio.to_thread(do_say, str(msg["text"])[:300])
    elif kind == "run" and msg.get("task"):
        await asyncio.to_thread(do_task, str(msg["task"])[:200])


def read_room() -> dict:
    """What Home Assistant knows about the room right now, in Nucleus shape."""
    req = urllib.request.Request(f"{HA_URL}/api/states", headers={"Authorization": f"Bearer {HA_TOKEN}"})
    with urllib.request.urlopen(req, timeout=8) as r:
        states = json.loads(r.read())
    room = {"type": "room", "ha": True, "board": None}
    for s in states:
        eid, st, attrs = s.get("entity_id", ""), s.get("state"), s.get("attributes", {})
        if "jarvis_desk" not in eid:
            continue
        try:
            if eid.startswith("sensor.") and eid.endswith("room_temperature"):
                room["temp"] = float(st)
            elif eid.startswith("sensor.") and eid.endswith("room_humidity"):
                room["hum"] = float(st)
            elif eid.startswith("light.") and eid.endswith("desk_strip"):
                room["board"] = st != "unavailable"
                room["strip"] = {"on": st == "on", "rgb": attrs.get("rgb_color") or [0, 0, 0],
                                 "effect": attrs.get("effect") or "None"}
            elif eid.startswith("binary_sensor.") and eid.endswith("room_motion"):
                room["motion"] = st == "on"
            elif eid.startswith("switch.") and eid.endswith("motion_mode"):
                room["motion_mode"] = st == "on"
            elif eid.startswith("number.") and eid.endswith("night_starts"):
                room.setdefault("night", [23, 8])[0] = int(float(st))
            elif eid.startswith("number.") and eid.endswith("night_ends"):
                room.setdefault("night", [23, 8])[1] = int(float(st))
        except (TypeError, ValueError):
            pass
    return room


async def room_loop() -> None:
    while True:
        try:
            HUB.emit(await asyncio.to_thread(read_room))
        except Exception:
            HUB.emit({"type": "room", "ha": False})
        await asyncio.sleep(ROOM_POLL)


async def main() -> None:
    if not KEY_FILE.exists():
        sys.exit(f"Missing {KEY_FILE}. Put your Anthropic API key in it.")
    ws_url = HA_URL.replace("http", "ws", 1) + "/api/websocket"
    start_photo_drop()
    await HUB.serve()
    asyncio.ensure_future(room_loop())
    hud(type="queue", **queue_counts())
    while True:
        try:
            async with websockets.connect(ws_url, max_size=None) as ws:
                await ws.recv()
                await ws.send(json.dumps({"type": "auth", "access_token": HA_TOKEN}))
                if json.loads(await ws.recv()).get("type") != "auth_ok":
                    sys.exit("Home Assistant refused the token in ha-token.txt.")
                await ws.send(json.dumps({"id": 1, "type": "subscribe_events",
                                          "event_type": "jarvis_task"}))
                await ws.recv()
                await ws.send(json.dumps({"id": 2, "type": "subscribe_events",
                                          "event_type": "jarvis_reel"}))
                await ws.recv()
                log(f"Bridge {VERSION} ready (tasks + digests + Nucleus). "
                    "Say \"Hey Jarvis, task: ...\"  Ctrl+C to stop.")
                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("type") != "event":
                        continue
                    etype = msg["event"].get("event_type")
                    data = msg["event"].get("data") or {}
                    if etype == "jarvis_reel":
                        url = (data.get("url") or "").strip()
                        if url.startswith("http"):
                            save_reel(url)
                        continue
                    task = (data.get("task") or "").strip()
                    if not task:
                        continue
                    await asyncio.to_thread(do_task, task)
        except (OSError, websockets.WebSocketException) as e:
            log(f"Lost Home Assistant ({e}); retrying in 10 s...")
            await asyncio.sleep(10)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTask bridge off.")
