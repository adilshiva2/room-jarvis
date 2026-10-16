# Changelog

Dated, in plain words. Older history (Oct 1-13) was squashed when secrets were removed from git on Oct 14.

## 2026-10-15
- The Nucleus: `jarvis-nucleus.html`, Jarvis's face on the monitor. Reacts to the room's sound (mic), shows listening / heard / reply / speaking, becomes a progress ring during tasks (stages), room telemetry, queues, clickable tiles and a typed command line. Keys: F fullscreen, D demo, / type.
- Bridge v7: serves the Nucleus (port 8802), streams events to it (ws 8803), accepts `/event` posts from the ears, takes typed commands (Home Assistant conversation API) and tile clicks (tasks), polls room telemetry, one task at a time.
- Ears report their moments to the Nucleus (`JARVIS_HUD_URL`, defaults to the local bridge).
- S330 speakerphone is Jarvis's voice, on the Mac (the Pi and a powered USB-A hub both brown out on its start-up surge; Pi move waits for a 3 A-capable part). AnkerWork firmware updated.
- Home Assistant automation "Jarvis strip - colour beats effect": a spoken colour now overrides a running effect.
- Pi doctor reads `board-password.txt`. Board web page can hang while everything else keeps working; power-cycle fixes it.
- Clean one-commit history pushed; repo public.

## 2026-10-14
- Reel digest v2: local transcription (yt-dlp + faster-whisper), insight-focused prompt, Word doc, emailed via Gmail SMTP, spoken takeaways.
- Recruiting digest: "Photo to Jarvis" shortcut → phone POSTs screenshots to the Mac (port 8802) → agent reads them, appends tracker rows, drafts outreach from a voice guide built from five real messages, emails Word digest + Excel tracker.
- Bridge v6: folder layout `~/jarvis-tasks/{tasks,logs,reels,recruiting}`; version banner; logs what Whisper heard; broad routing words.
- Secrets moved out of code: `secrets.yaml` for ESPHome, `board-password.txt` for server and doctor. Git history squashed.
- Repo organized: README, docs, learning notes, scripts, requirements, HA automations as files.
- Party Kart v3 (side project) moved to `~/games/party-kart`.

## 2026-10-13
- Mind layer 1: Claude Sonnet 5.5 as the conversation brain in Home Assistant ($20/month cap).
- Task bridge: "Hey Jarvis, task: ..." runs a Claude agent in a sandboxed folder, speaks the summary.
- Voice modes fixed (one color descriptor per light.turn_on). Motion Mode rename. Room plan.
- Jarvis Doctor on the Pi, every 5 minutes.

## 2026-10-12
- Night window and wake cooldown on the board; motion sensor aimed at the door.

## 2026-10-11
- Mac wake-word ears (openWakeWord → HA assist pipeline). On-board motion rule.

## 2026-10-10
- Phase F: Pi with Home Assistant in Docker, board paired. Phase G1a: Whisper + Piper, Jarvis assistant, voice from the phone.

## 2026-10-07 / 08
- WiFi board (ESPHome), HUD app, lock-down (board password, HUD PIN), Jarvis effects, bCourses study puller.

## 2026-10-01 → 06
- Parts, first blink, strip lit, sensor read.
