# Runbook

Everything you need to start, stop, check, and fix Jarvis. Written for future-me at 2 a.m.

## Which window am I in?

- `adilshivakumar@Adils-MacBook-Air-2 ~ %` → the **Mac**. Ends with `%`.
- `adil@jarvis-pi:~ $` → the **Pi**. Ends with `$`. Get there with `ssh adil@jarvis-pi.local`, leave with `exit`.
- `(jarvis-env)` or `(jarvis-ears-env)` at the front = a Python toolbox is active. Harmless.

## Start the Mac side (two tabs)

```
~/jarvis/scripts/start-ears.sh      # tab 1: "Hey Jarvis" listener
~/jarvis/scripts/start-bridge.sh    # tab 2: task bridge + digests + photo drop
```
(or `ears` if the alias is set: `echo "alias ears='~/jarvis/scripts/start-ears.sh'" >> ~/.zshrc`)

Exactly **one** of each. Two bridges = two voices answering. Fix: `pkill -f jarvis-tasks.py; pkill -f jarvis-ears.py`, then start again.

The bridge prints `Bridge v6 ready` and `Photo drop ready: http://...local:8802/photo` when it's up.

## The Pi side (starts itself)

Home Assistant, Whisper, Piper run in Docker and restart on boot. The HUD server and the Doctor are systemd units.

```
docker ps                                   # three containers "Up"
sudo systemctl status jarvis                # HUD server
sudo python3 /home/adil/jarvis/jarvis-doctor.py report   # full health report
```

## Flash the board

```
cd ~/jarvis && source ~/jarvis-env/bin/activate && esphome run jarvis-node1.yaml
```
Needs `secrets.yaml` next to the YAML. Over the air works when the strip is **off** (an animation can starve the upload: "Connection reset by peer"). If `.local` won't resolve: `--device 192.168.0.215`. If OTA keeps failing: plug in USB and pick the usbserial port — always works. A failed OTA cannot brick the board.

Expect warnings about framework, strapping pin GPIO5, chip revision. Normal. First WiFi attempt after boot often fails; the second connects.

## Voice commands that exist

| Say | Does |
|---|---|
| turn on / off the desk strip, set it to magenta | Tier 0, on the board |
| what's the room temperature | Tier 0 |
| movie mode / focus mode / jarvis mode / good night | automations (good night also turns Motion Mode off) |
| turn on motion mode | re-enable walk-in wake |
| anything else | Sonnet answers |
| task: ... | the agent runs it; "task: reel digest", "task: recruiting digest" are special |

## Day-to-day

- **Save a reel:** Instagram → Share → Reel to Jarvis. Free. Run "task: reel digest" once a week.
- **Save a job post:** screenshot → Share → Photo to Jarvis. Bridge prints "Screenshot received". Run "task: recruiting digest".
- **Outputs:** `~/jarvis-tasks/reels/digests/`, `~/jarvis-tasks/recruiting/digests/`, `~/jarvis-tasks/recruiting/drafts/`, and your email.
- **Tune the agent's voice:** edit `~/jarvis-tasks/recruiting/voice-guide.md`.

## Things that look broken but aren't

- Lights don't wake in the morning before 8 → night window (Night Ends in HA).
- Lights don't wake while you sit there → it wakes on *arrival* only (room empty 5 min first).
- Jarvis says "Done" instead of the custom reply → an automation action is invalid (classic: two color descriptors in one light.turn_on). Automations → Traces.
- Board web page "FAIL" in the Doctor but entities live → web server busy; transient.

## When it's actually broken

| Symptom | Do |
|---|---|
| "Sorry, I am not aware of any device called ..." | Settings → Voice assistants → Expose; add an alias without the device name |
| Two voices | one bridge, one ears (see above) |
| Agent says "web access was denied" | bridge is old; restart it |
| Task went to the wrong pipeline | read the `Heard:` line; Whisper mishears "reel" as "real" (handled), say "screenshots" for recruiting |
| Email didn't arrive | `gmail-app-password.txt` present? Gmail 2-step on? bridge log says "Email failed: ..." |
| Phone can't reach the Mac | same WiFi? firewall prompt allowed? address ends in `.local:8802/photo`? |
| Pi password rejected | you're in the Mac window |

## Secrets (never in git)

`~/jarvis/secrets.yaml` (board), `ha-token.txt`, `anthropic-key.txt`, `gmail-app-password.txt`, `board-password.txt`, `canvas-token.txt`. The Pi has its own `ha-token.txt` and `board-password.txt` in `/home/adil/jarvis/`.

To rotate the board's passwords: edit `secrets.yaml`, flash, then update `board-password.txt` on both machines and re-enter the API key in HA (Settings → Devices → ESPHome → Configure). OTA password changes need a USB flash.
