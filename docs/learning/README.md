# Learning notes

One note per layer of Jarvis, written to answer "what is this code actually doing, and why that way?" Read them in order the first time; after that, jump to whichever one you're touching.

1. [ESPHome and the board](01-esphome-and-the-board.md) — YAML that becomes firmware, lambdas, globals, why the motion logic lives on the chip
2. [Home Assistant](02-home-assistant.md) — entities, automations, sentence triggers, exposing things to Assist, webhooks, events
3. [The voice pipeline](03-voice-pipeline.md) — openWakeWord → assist pipeline → Whisper → intent → Piper, and the Wyoming protocol
4. [The bridge](04-the-bridge.md) — websockets, asyncio, running a headless Claude agent, permission modes, why it's shaped the way it is
5. [Agents and cost](05-agents-and-cost.md) — tiers, tokens, what a run costs, how to keep it cheap
6. [Networking](06-networking.md) — LAN, mDNS `.local`, ports, why the phone can reach the Mac and the internet can't
7. [Security](07-security.md) — secrets out of git, allow-listed tools, account-safe design, what to rotate
