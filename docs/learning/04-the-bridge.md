# 4. The bridge (`jarvis-tasks.py`)

The bridge is the piece that makes Jarvis *do* things rather than answer things. One Python file, three jobs:

1. Listen to Home Assistant events and run a Claude agent for voice tasks.
2. Catch reel links (free) and, on request, transcribe + digest them.
3. Receive screenshots from the phone (port 8802) and, on request, turn them into tracker rows and outreach drafts.

## Shape of the program

```
main()           websocket loop: auth → subscribe to jarvis_task + jarvis_reel → for each event: route
run_task()       keyword router → run_recruiting() | run_digest() | run_agent() (generic)
run_agent()      the only place the Claude CLI is invoked
speak()          HA Piper → mp3 → afplay
PhotoDrop        tiny HTTP server in a thread, POST /photo → recruiting/inbox/
helpers          fetch_reel, transcribe, prepare_reels, md_to_docx, csv_to_xlsx, send_email
```

## asyncio and threads

The websocket loop is `async`. The agent run can take minutes and `subprocess.run` blocks, so it's wrapped in `await asyncio.to_thread(run_task, task)`: the blocking work moves to a worker thread while the loop keeps the websocket alive (otherwise HA would drop the connection mid-task). `speak()` is wrapped the same way. The photo-drop HTTP server runs in its own daemon thread from the start.

The outer `while True / try / except` is the reconnect loop: if the Pi reboots, the bridge logs "Lost Home Assistant", sleeps 10 s, and re-subscribes. No restart needed.

## Running Claude headless

```python
["claude", "-p", prompt, "--model", "claude-sonnet-5-5",
 "--permission-mode", "acceptEdits",
 "--allowedTools", "WebFetch", "WebSearch", "Bash(curl:*)"]
```

- `-p` = print mode: one prompt in, final text out, no interactive session. Perfect for a subprocess.
- `cwd=workdir` sets the agent's working folder. In `acceptEdits` mode it may read/write/edit **inside that folder** without asking; anything that needs another permission can't be granted (nobody is watching) and fails — that's the sandbox.
- `--allowedTools` is the allow-list beyond edits: read-only web plus `curl`. Nothing else on the Mac.
- `env=` is deliberately minimal: a fixed PATH, HOME, and the API key read from `anthropic-key.txt`. The key never touches the shell history.
- `timeout=TASK_TIMEOUT` (15 min) kills a runaway run; `subprocess.TimeoutExpired` becomes a spoken "hit the limit".

The prompts end with a strict instruction: finish with one `SUMMARY:` line. The bridge takes the last such line as speech. It's a contract between the program and the model.

## Why prompts are templates in the file

The digest and recruiting prompts are long and specific ("never ask Adil for anything", "write digests/reel-digest-TODAY.md", "never invent facts"). Keeping them as constants next to the code that depends on their output (file names, SUMMARY line) means one file to read when behavior changes. Each hard rule in them came from a real failure: the agent once asked the user to paste a caption (unattended runs can't), once reused an old digest (now moved aside before each run), once described reels instead of extracting their substance.

## The free stages

`prepare_reels()` runs **before** any tokens are spent: yt-dlp pulls audio (`bestaudio[ext=m4a]`), faster-whisper transcribes it on the Mac CPU (`small.en`, int8). Each reel becomes `reels/work/reel-N.txt` with link, creator, caption, transcript. The agent reads those files; it never fetches Instagram itself.

`collect_screenshots()` moves images from `recruiting/inbox/` (and, if iCloud ever syncs, from the iCloud folders), converts HEIC → JPG with pillow-heif so the agent can view them.

## Output conversion

`md_to_docx()` is a 30-line Markdown → Word converter (headings, bullets, bold, links as text) using python-docx — enough for the digest shape the prompt dictates. `csv_to_xlsx()` uses openpyxl: bold header, auto column widths, frozen top row. `send_email()` is `smtplib.SMTP_SSL` to Gmail with an **App Password** (not the account password) and `EmailMessage` attachments with the right MIME subtypes so phones preview them.

## Routing by words

Whisper is imperfect, so routing is forgiving: any of "recruit / screenshot / photo / LinkedIn / job" → recruiting; "digest" (or "reel/real" + "summar…") → reels; otherwise generic. The `Heard:` log line exists because the first debugging question is always "what did it think I said?".

## Go deeper

Python docs: `asyncio.to_thread`, `subprocess.run`. Claude Code docs: *CLI reference* (`-p`, `--permission-mode`, `--allowedTools`). Try: add a `jarvis_note` event + "note {text}" sentence that appends to `tasks/notes.md` — no agent, no tokens.
