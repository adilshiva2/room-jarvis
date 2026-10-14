# Architecture

How a sentence spoken in the room turns into something happening.

## The three machines

| Machine | Role | Always on? | Address |
|---|---|---|---|
| ESP32 "jarvis-node1" | The body: 60-LED strip (GPIO5), DHT22 temperature/humidity (GPIO4), PIR motion (GPIO18). Runs ESPHome firmware; makes its own decisions about motion. | yes | 192.168.0.215, web page with password |
| Raspberry Pi 5 "jarvis-pi" | The brain: Home Assistant (Docker), Whisper (speech → text), Piper (text → speech), the HUD server, the Doctor. | yes | jarvis-pi.local / 192.168.0.213, HA on :8123 |
| MacBook Air | The mind's hands: wake-word ears (for now), the task bridge, the Claude agent, local reel transcription. | when awake | Adils-MacBook-Air-2.local, photo drop on :8802 |

## Flow 1: a light command ("movie mode")

1. `jarvis-ears.py` hears "Hey Jarvis" (openWakeWord, on the Mac mic), chimes, and opens a websocket to Home Assistant's **assist pipeline**, streaming raw 16 kHz audio.
2. Home Assistant forwards audio to **Whisper** (Wyoming protocol, port 10300) → text: "movie mode".
3. Home Assistant's conversation layer matches a **sentence trigger** in an automation (`home-assistant/automations.yaml` → "Jarvis: movie mode"). The automation calls `light.turn_on` on the strip with brightness and color, and sets a spoken response.
4. Home Assistant talks to the board over the **ESPHome native API** (TCP 6053, encrypted with the key in `secrets.yaml`). The strip changes.
5. The response text goes to **Piper** (port 10200) → an MP3 URL. The ears program downloads and plays it.

Nothing left the house. Round trip ~1 s.

## Flow 2: a question ("what's a tariff?")

Same as flow 1 through step 2. No sentence matches, and "prefer handling locally" finds no built-in intent, so Home Assistant hands the text to the **Anthropic integration** (Claude Sonnet 5.5, max 300 response tokens, with the Jarvis persona in the system prompt). The answer comes back, Piper speaks it. ~0.25 cent.

## Flow 3: a task ("task: reel digest")

1. The sentence trigger `task {task}` fires the **Jarvis task bridge** automation, which does two things: sends an event `jarvis_task` with the text, and replies "On it, sir" immediately so the voice loop closes.
2. `jarvis-tasks.py` on the Mac holds a websocket subscription to HA events. It receives `jarvis_task`, logs what it heard, and routes by keyword: recruit/screenshot/photo → recruiting digest; digest → reel digest; anything else → a generic task.
3. For a generic task it builds a prompt from a template (who Jarvis is, the task, the rules, "end with a SUMMARY line") and runs `claude -p <prompt> --permission-mode acceptEdits --allowedTools WebFetch WebSearch "Bash(curl:*)"` with the working directory set to `~/jarvis-tasks/tasks`. That is the whole sandbox: the agent may edit inside that folder without asking and read the web; anything else needs a permission nobody is there to grant, so it fails safely.
4. The agent's final `SUMMARY:` line becomes speech: Piper via HA's `tts_get_url`, played with `afplay`.

For the **reel digest**, step 3 is preceded by a free local stage: each saved link is downloaded with yt-dlp (audio only) and transcribed on the Mac with faster-whisper; the agent then works from the transcripts, writes the digest, and the bridge converts it to Word and emails it over Gmail SMTP.

For the **recruiting digest**, the bridge first collects screenshots from `recruiting/inbox/` (put there by the phone's POST to port 8802), the agent reads each image directly, appends tracker rows, writes drafts from the voice guide, and the bridge emails the Word digest plus an Excel export of the tracker.

## Flow 4: motion (no voice)

Lives entirely on the board. On PIR rise: wake the strip only if Motion Mode is on, it isn't night (window set from HA), the strip is off, the room was empty 5+ minutes, nobody manually turned it off within 15 minutes, and no auto-wake happened within 30 minutes. On PIR fall: start a 10-minute sleep timer. The reasoning is in the `on_press` lambda in `jarvis-node1.yaml`.

## Flow 5: health (every 5 minutes)

A systemd timer on the Pi runs `jarvis-doctor.py check`. It verifies the HUD service, the three containers, the HA API, the board's web page, every `jarvis_desk` entity's state, disk, and CPU temperature; restarts the service or containers if down; appends one line to `doctor.log`. `jarvis-doctor.py report` prints the current state plus the last 25 lines — the thing to paste when something feels off.

## Where state lives

| What | Where |
|---|---|
| Board behavior (effects, motion rules) | firmware, from `jarvis-node1.yaml` |
| Night window, Motion Mode, Auto Wake | on the board, restored across reboots, editable from HA |
| Automations, voice assistant config, API keys | Home Assistant's own storage on the Pi |
| Task outputs, logs, reels, recruiting | `~/jarvis-tasks/` on the Mac (not in git) |
| Secrets | `secrets.yaml`, `ha-token.txt`, `anthropic-key.txt`, `gmail-app-password.txt`, `board-password.txt` — all gitignored |

## Ports

| Port | Service | Reachable from |
|---|---|---|
| 80 | board web page | LAN, password |
| 6053 | ESPHome native API | HA only, encrypted |
| 8123 | Home Assistant | LAN |
| 10300 / 10200 | Whisper / Piper (Wyoming) | Pi localhost only |
| 8000 | HUD server | LAN, PIN |
| 8802 | photo drop on the Mac | LAN |
| 8800 / 8801 | Party Kart (separate project) | LAN |
