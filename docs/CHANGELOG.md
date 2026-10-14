# Changelog

Dated, in plain words. Older history (Oct 1-13) was squashed when secrets were removed from git on Oct 14.

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
