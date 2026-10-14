# 3. The voice pipeline

**Files:** `jarvis-ears.py` (Mac), Docker containers `whisper` and `piper` (Pi), the Jarvis assistant in HA.

## The chain

```
mic → openWakeWord ("Hey Jarvis"?) → chime → stream audio to HA assist pipeline
    → Whisper (STT) → text → intent / Sonnet → reply text → Piper (TTS) → mp3 → speaker
```

## Wake word (on the Mac, for now)

`jarvis-ears.py` opens the microphone with `sounddevice` at **16 kHz, mono, 16-bit** — the format every piece downstream expects — in chunks of 1280 samples (80 ms). Each chunk goes to openWakeWord's `hey_jarvis` model, which returns a score 0–1. Above `WAKE_THRESHOLD` (0.5) it's a wake. Lower = more sensitive, more false wakes.

The audio callback runs on a separate thread, so it hands chunks to an `asyncio.Queue` via `call_soon_threadsafe` — the only safe way to cross from a thread into the asyncio loop. `drain()` empties the queue after the chime so the chime itself isn't sent as your command.

## Streaming to Home Assistant

The ears open the HA websocket, authenticate, and send `assist_pipeline/run` with `start_stage: stt`, `end_stage: tts`. HA answers with a `run-start` event containing `stt_binary_handler_id` — a one-byte prefix. From then on every audio chunk is sent as a **binary** websocket frame: `bytes([handler]) + chunk`. An empty frame with just the handler byte means "I'm done talking".

HA sends events as it goes: `stt-vad-end` (it heard you stop), `stt-end` (with the text), `intent-end` (with the reply), `tts-end` (with the audio URL), `run-end`. The ears print the text and reply, download the mp3, and play it with `afplay`.

## Wyoming

Whisper and Piper don't run inside HA. They're separate programs speaking the **Wyoming protocol** — a tiny line-oriented protocol (JSON header + binary audio) on TCP 10300 / 10200. HA's Wyoming integration connects to them. Benefit: you can swap the STT engine, run it on another machine, or scale it without touching HA.

- **faster-whisper** `base-int8`: good accuracy for short commands, ~1 s on the Pi 5. `small` is more accurate but slower; `tiny` is faster but mishears more. Known mishear: "reel" → "real".
- **Piper** `en_GB-alan-medium`: the British voice. Medium = quality/speed balance for a Pi.

## Where it decides

After STT, HA's **conversation** step runs: sentence triggers from automations first, then built-in intents (turn on X, what's the temperature), then — because "prefer handling locally" found nothing — the Anthropic conversation agent. That order is the cost control: free paths are tried before the paid one.

## Moving the ears to the Pi (Phase G2)

Same program, three changes: `sounddevice` picks the S330 as input device, `PLAYER` becomes `["mpv", "--no-video"]` or `aplay`, and it runs as a systemd service so it starts on boot. The S330 is a USB audio class device, so Linux sees it as both a capture and a playback card (`arecord -l` / `aplay -l`).

## Go deeper

openWakeWord README (training your own wake word takes an afternoon). HA docs: *Assist pipeline*, *Wyoming*. Try: `WAKE_THRESHOLD = 0.35` and count false wakes in an evening.
