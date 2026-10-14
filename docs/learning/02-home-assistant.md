# 2. Home Assistant

**Runs:** in Docker on the Pi, `--network host`, data in a bind-mounted folder. **URL:** http://jarvis-pi.local:8123.

## The mental model

Home Assistant (HA) is a state machine with a bus. Every device, sensor, switch, and helper is an **entity** with an id (`light.jarvis_desk_desk_strip`), a **state** (`on`), and **attributes** (brightness, rgb_color). Integrations (ESPHome, Wyoming, Anthropic) create entities and keep them updated. Everything else — automations, voice, the API — reads and writes entities or listens on the **event bus**.

## Entities you have

| Entity | From | Notes |
|---|---|---|
| `light.jarvis_desk_desk_strip` | ESPHome | brightness, rgb_color, effect |
| `sensor.jarvis_desk_room_temperature` / `_humidity` | ESPHome | updates every 10 s |
| `binary_sensor.bedroom_jarvis_desk_room_motion` | ESPHome | note the `bedroom_` prefix (created in an area) |
| `switch.jarvis_desk_auto_wake`, `switch.bedroom_jarvis_desk_motion_mode` | ESPHome template switches | state lives on the board |
| `number.bedroom_jarvis_desk_night_starts` / `_ends` | ESPHome template numbers | editable, restored on the board |

## Automations

An automation = triggers + (optional) conditions + actions. Ours use two trigger types:

- **conversation** (sentence) triggers: `command: ["movie mode"]`. When Assist hears that sentence, the automation runs, and `set_conversation_response` is what Jarvis says back. Slots like `task {task}` capture the rest of the sentence into `trigger.slots.task`.
- **webhook** triggers: `webhook_id: jarvis-reel-7g2k`, `local_only: true`. An HTTP POST to `/api/webhook/<id>` from the LAN runs it; the JSON body is `trigger.json`. No token needed — the random id is the secret.

Actions we use: `light.turn_on` (with data), `switch.turn_off`, `event` (fire a custom event on the bus), `set_conversation_response`. The exact YAML is in `home-assistant/automations.yaml`.

**Modes:** `mode: queued` lets several tasks line up instead of being dropped.

**Traces:** Settings → Automations → ⋮ → Traces shows every run step by step. This is how the "two color descriptors" bug was found: the action errored and the response never ran, so Jarvis just said "Done".

## Assist and exposure

Voice only sees entities you **expose** (Settings → Voice assistants → Expose). Assist prepends the device name when matching, so "Room Motion" on device "Jarvis Desk" is matched as "Jarvis Desk Room Motion" — add an **alias** ("motion mode") so plain speech works. Watch for clashes: an alias "lights" on the strip made "turn off motion lights" turn off the strip.

"Prefer handling commands locally" = try built-in intents first (free, fast); only if nothing matches, send to the conversation agent (Claude).

## The APIs we talk to

- **REST** `/api/states`, `/api/tts_get_url` with a long-lived token in `Authorization: Bearer`. The Doctor and the bridge's TTS use this.
- **WebSocket** `/api/websocket`: authenticate, then `subscribe_events` (the bridge listens for `jarvis_task` and `jarvis_reel`) or `assist_pipeline/run` (the ears stream audio through it). Every message has an `id`; replies echo it.
- **Events** are the glue between HA and the Mac: an automation fires `event: jarvis_task` with data, the bridge receives `{"type":"event","event":{"event_type":"jarvis_task","data":{...}}}`. Fire-and-forget, no polling.

## Go deeper

HA docs: *Automation YAML*, *Sentence triggers*, *WebSocket API*, *Webhook trigger*. Try: add a `template` sensor "room comfort" that's "stuffy" above 60 % humidity, expose it, ask Jarvis.
