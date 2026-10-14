# 1. ESPHome and the board

**File:** `jarvis-node1.yaml`. **Chip:** ESP32 (dual-core, WiFi, 520 KB RAM). **Flash:** `esphome run jarvis-node1.yaml`.

## What ESPHome is

ESPHome turns a YAML description into C++ firmware. You never write the main loop; you declare *components* (a light on this pin, a sensor on that pin) and *automations* (when X, do Y), and ESPHome generates the program, compiles it with PlatformIO, and uploads it. The first upload is over USB; afterwards the board accepts updates over WiFi (OTA) protected by `ota_password`.

The board then speaks the **ESPHome native API** on TCP 6053. Home Assistant connects to it, encrypted with `api_key`, and every component with a `name:` becomes an HA entity: `light.jarvis_desk_desk_strip`, `sensor.jarvis_desk_room_temperature`, and so on. The entity id = device friendly name + component name, which is why renaming "Motion Lights" to "Motion Mode" created a new entity id (and why some ids got a `bedroom_` prefix: they were created while the device sat in the Bedroom area).

## Reading the file top to bottom

- `esphome:` / `esp32:` — identity and chip. `upload_speed: 115200` because this board's USB chip drops bytes at the default.
- `api:` `ota:` `wifi:` `web_server:` — the four ways in. All four take `!secret` values from `secrets.yaml`. `ap:` is a fallback hotspot the board opens if WiFi fails, so you can fix the password without a cable.
- `globals:` — variables that survive between automations. `last_motion_end`, `last_manual_off`, `last_auto_wake` are timestamps in milliseconds since boot (`millis()`); `auto_off_now` is a flag that tells `on_turn_off` "this off was me, not the human".
- `switch: template` — a software switch with no pin. `optimistic: true` means the switch *is* its state (nothing to read back). `restore_mode: RESTORE_DEFAULT_ON` keeps it across reboots, defaulting on.
- `script:` — named sequences. `mode: restart` means calling it again restarts the delay, which is exactly what a sleep timer needs.
- `light: esp32_rmt_led_strip` — the strip, driven by the ESP32's RMT peripheral (hardware timing, so WiFi interrupts don't glitch the colors). `rgb_order: GRB` because WS2812B chips take green first. Effects are either built-in (`pulse`, `addressable_scan`, `addressable_rainbow`) or `addressable_lambda`: C++ that runs every `update_interval` and gets `it`, the array of LEDs.
- `time: homeassistant` — the board has no clock of its own; it asks HA for the time. `t.is_valid()` is false until that first sync, which is why the night check guards on it.
- `number: template` — editable numbers that live on the board (`restore_value: true`) and show as sliders in HA. The night window is two of these, so changing it never needs a reflash.
- `sensor: dht` — DHT22 is slow (one reading per 2 s minimum) and a little noisy. `on_value` keeps a running baseline (`hum_base`, exponential average) and fires the wake when humidity jumps 2.5 points above it — that's the "someone walked in from the shower" trick.
- `binary_sensor: gpio` with `delayed_on: 200ms` — the PIR output is HIGH while it sees motion. The filter ignores sub-200 ms blips.

## Lambdas

A `lambda:` block is literal C++ dropped into the generated code. `id(name)` gets a component or global. `.state` reads a switch; `id(desk_strip).remote_values.is_on()` reads the *last commanded* light state. `millis()` is milliseconds since boot and wraps every 49 days — subtracting two unsigned values still works across the wrap, which is why the code compares differences, never absolute times.

## Why the motion logic is on the board and not in Home Assistant

It was in HA first (a blueprint automation). Two problems: the Pi can restart or lag, and the automation kept fighting manual control. On the chip the rule runs in microseconds, survives the Pi being down, and has direct access to "did the human just turn this off" — a fact only the board knows for sure. HA still gets the sensor state for everything else.

## Things that bit me

- A running effect repaints the strip every frame, so "set color magenta" looks ignored: turn the effect off (`effect: none`) first, then set color.
- OTA uploads fail while an animation runs (the RMT and WiFi share CPU). Turn the strip off before flashing.
- Two light attributes from different "color groups" in one `light.turn_on` (e.g. `rgb_color` and `color_temp`) is a validation error in HA, and the automation silently stops.
- GPIO5 is a "strapping pin": it must be in the right state at boot. It works for a data line, the warning is just a warning.

## Go deeper

ESPHome docs: *Automations and Templates* (lambdas), *ESP32 RMT LED Strip*, *Native API Component*. Try: add a `button:` template that runs `jarvis_wake` so you can trigger the animation from HA.
