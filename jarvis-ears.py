#!/usr/bin/env python3
"""Jarvis ears: listen for "Hey Jarvis", send what you say next to Home Assistant, play the answer.

Runs on the Mac or on the Pi; it picks the right audio devices and player by itself.
If a device whose name contains EARS_DEVICE (the Anker S330) is present, it is used for
the microphone; otherwise the system default. The reply plays through the system default
output (set the S330 as default output in Sound settings on the Mac, or via the installer
on the Pi). Needs: ha-token.txt next to this file. Stop with Ctrl+C.

It also tells the Nucleus (the face on the monitor) what is happening: listening,
what it heard, Jarvis's reply, speaking. Those go as tiny POSTs to the task bridge
(HUD_URL); if the bridge is not running they are silently dropped. When the ears
run on the Pi, set JARVIS_HUD_URL to the Mac, e.g.
http://Adils-MacBook-Air-2.local:8802/event

On the Pi it runs as a service: see pi/install-ears.sh.
"""
import asyncio
import json
import os
import pathlib
import platform
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

import numpy as np
import sounddevice as sd
import websockets
import openwakeword.utils
from openwakeword.model import Model

# ---- settings you might change ----
HA_URL = "http://jarvis-pi.local:8123"  # or "http://192.168.0.213:8123"
EARS_DEVICE = "S330"  # part of the mic's name to prefer (Anker PowerConf S330); default mic if absent
WAKE_THRESHOLD = 0.5  # lower = wakes more easily (and by mistake more often)
MAX_LISTEN_SECONDS = 8  # longest command it will listen to
HUD_URL = os.environ.get("JARVIS_HUD_URL", "http://127.0.0.1:8802/event")  # the bridge's event door
# ------------------------------------

IS_MAC = platform.system() == "Darwin"
HERE = pathlib.Path(__file__).resolve().parent
TOKEN_FILE = HERE / "ha-token.txt"
CHIME = "/System/Library/Sounds/Tink.aiff" if IS_MAC else str(HERE / "chime.wav")
MP3_PLAYER = ["afplay"] if IS_MAC else ["mpg123", "-q"]       # Piper replies arrive as mp3
WAV_PLAYER = ["afplay"] if IS_MAC else ["aplay", "-q"]        # the chime
RATE = 16000  # what the wake word model and Whisper expect
FRAME = 1280  # 80 ms of audio per chunk at 16 kHz


def find_input_device():
    """Index of the first input device whose name contains EARS_DEVICE, else None (= default)."""
    try:
        for i, d in enumerate(sd.query_devices()):
            if EARS_DEVICE.lower() in d["name"].lower() and d["max_input_channels"] > 0:
                print(f"Mic: {d['name']}")
                return i
    except Exception:
        pass
    print("Mic: system default")
    return None


def make_chime() -> None:
    """On Linux there is no system sound file; write a short two-tone chime once."""
    if IS_MAC or pathlib.Path(CHIME).exists():
        return
    import wave
    sr = 22050
    t = np.linspace(0, 0.12, int(sr * 0.12), endpoint=False)
    tone = np.concatenate([np.sin(2 * np.pi * 880 * t), np.sin(2 * np.pi * 1320 * t)])
    env = np.minimum(1, np.linspace(0, 8, tone.size)) * np.linspace(1, 0.2, tone.size)
    pcm = (tone * env * 12000).astype(np.int16)
    with wave.open(CHIME, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())


def hud(**event) -> None:
    """Tell the Nucleus about a moment. Fire-and-forget; never slows the ears down."""
    def post():
        try:
            req = urllib.request.Request(HUD_URL, data=json.dumps(event).encode(),
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=1.5).read()
        except Exception:
            pass
    threading.Thread(target=post, daemon=True).start()


def drain(q: asyncio.Queue) -> None:
    """Throw away audio that piled up while Jarvis was busy."""
    while not q.empty():
        q.get_nowait()


def play(path: str) -> None:
    player = WAV_PLAYER if path.endswith((".wav", ".aiff")) else MP3_PLAYER
    subprocess.run(player + [path], check=False)


async def ask_home_assistant(token: str, q: asyncio.Queue) -> None:
    """Stream the microphone to Home Assistant's Jarvis pipeline and play the reply."""
    ws_url = HA_URL.replace("http", "ws", 1) + "/api/websocket"
    async with websockets.connect(ws_url, max_size=None) as ws:
        await ws.recv()  # auth_required
        await ws.send(json.dumps({"type": "auth", "access_token": token}))
        if json.loads(await ws.recv()).get("type") != "auth_ok":
            sys.exit("Home Assistant refused the token. Make a new one and paste it into ha-token.txt.")

        await ws.send(json.dumps({
            "id": 1,
            "type": "assist_pipeline/run",
            "start_stage": "stt",
            "end_stage": "tts",
            "input": {"sample_rate": RATE},
        }))

        handler = None
        while handler is None:
            msg = json.loads(await asyncio.wait_for(ws.recv(), 10))
            if msg.get("type") == "result" and not msg.get("success"):
                print("  Home Assistant said no:", msg.get("error"))
                return
            if msg.get("type") == "event" and msg["event"]["type"] == "run-start":
                handler = msg["event"]["data"]["runner_data"]["stt_binary_handler_id"]

        stop = asyncio.Event()

        async def send_audio() -> None:
            start = time.monotonic()
            while not stop.is_set():
                if time.monotonic() - start > MAX_LISTEN_SECONDS:
                    await ws.send(bytes([handler]))  # "I'm done talking"
                    return
                try:
                    chunk = await asyncio.wait_for(q.get(), 0.2)
                except asyncio.TimeoutError:
                    continue
                await ws.send(bytes([handler]) + chunk)

        sender = asyncio.create_task(send_audio())
        tts_url = None
        try:
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 30))
                if msg.get("type") != "event":
                    continue
                kind = msg["event"]["type"]
                data = msg["event"].get("data") or {}
                if kind == "stt-vad-end":
                    stop.set()  # Home Assistant heard you stop talking
                elif kind == "stt-end":
                    stop.set()
                    print("  You:   ", data["stt_output"]["text"])
                    hud(type="heard", text=data["stt_output"]["text"])
                elif kind == "intent-end":
                    speech = data["intent_output"]["response"]["speech"].get("plain", {}).get("speech", "")
                    print("  Jarvis:", speech)
                    hud(type="reply", text=speech)
                elif kind == "tts-end":
                    tts_url = data["tts_output"]["url"]
                elif kind == "error":
                    stop.set()
                    print("  Error: ", data.get("message"))
                    hud(type="log", text="ears: " + str(data.get("message"))[:80])
                elif kind == "run-end":
                    break
        finally:
            stop.set()
            await sender

    if tts_url:
        if tts_url.startswith("/"):
            tts_url = HA_URL + tts_url
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(urllib.request.urlopen(tts_url, timeout=15).read())
        hud(type="state", state="speaking")
        play(f.name)


def open_mic(device, loop, q):
    """Open the mic at 16 kHz; if the device only does 48 kHz, open that and downsample 3:1."""
    def cb16(indata, frames, when, status):
        loop.call_soon_threadsafe(q.put_nowait, bytes(indata))
    try:
        return sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=FRAME,
                                 device=device, callback=cb16)
    except Exception as e:
        print(f"(16 kHz not supported by this mic: {e}; using 48 kHz and downsampling)")

    def cb48(indata, frames, when, status):
        samples = np.frombuffer(indata, dtype=np.int16)
        down = samples.reshape(-1, 3).mean(axis=1).astype(np.int16)  # crude but fine for speech
        loop.call_soon_threadsafe(q.put_nowait, down.tobytes())
    return sd.RawInputStream(samplerate=48000, channels=1, dtype="int16", blocksize=FRAME * 3,
                             device=device, callback=cb48)


async def main() -> None:
    if not TOKEN_FILE.exists():
        sys.exit(f"Missing {TOKEN_FILE}. Paste your Home Assistant token into it.")
    token = TOKEN_FILE.read_text().strip()
    make_chime()

    print("Loading the 'Hey Jarvis' model (first run downloads it)...")
    openwakeword.utils.download_models(["hey_jarvis"])
    wake = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")

    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()
    device = find_input_device()

    with open_mic(device, loop, q):
        print("Listening. Say \"Hey Jarvis\", then your command. Ctrl+C to stop.")
        while True:
            chunk = await q.get()
            scores = wake.predict(np.frombuffer(chunk, dtype=np.int16))
            if max(scores.values()) >= WAKE_THRESHOLD:
                print("Heard \"Hey Jarvis\".")
                hud(type="state", state="listening")
                play(CHIME)
                drain(q)  # skip the chime itself
                try:
                    await ask_home_assistant(token, q)
                except (OSError, asyncio.TimeoutError, websockets.WebSocketException) as e:
                    print("  Couldn't reach Home Assistant:", e)
                    hud(type="log", text="ears: couldn't reach Home Assistant")
                hud(type="state", state="idle")
                wake.reset()
                drain(q)
                print("Listening.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nJarvis ears off.")
