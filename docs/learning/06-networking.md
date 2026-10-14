# 6. Networking

## One rule explains most of it

Everything lives on the home LAN (192.168.0.x). Devices on the same WiFi can reach each other; the internet cannot reach any of them. That's why the webhook needs no password (`local_only: true`), why the phone's screenshot goes straight to the Mac, and why none of this works from campus.

## Names

- `jarvis-pi.local`, `Adils-MacBook-Air-2.local` — **mDNS / Bonjour**: devices announce their own names on the LAN, no DNS server needed. iPhones and Macs resolve `.local` natively; it occasionally fails (then use the IP).
- `192.168.0.215` (board), `.213` (Pi) — DHCP leases that have stayed stable. If the router ever reassigns them, the Doctor and the bridge settings need the new address (or reserve them in the router).

## Who talks to whom

| From → To | Port | Protocol | Auth |
|---|---|---|---|
| HA → board | 6053 | ESPHome native API | encryption key |
| browser → board | 80 | HTTP | basic auth |
| ears/bridge/Doctor → HA | 8123 | REST + WebSocket | long-lived token |
| HA → Whisper / Piper | 10300 / 10200 | Wyoming (TCP) | localhost only |
| HA → Anthropic | 443 | HTTPS | API key (only internet traffic) |
| phone → HA | 8123 | HTTP POST (webhook) | obscure id, LAN only |
| phone → Mac | 8802 | HTTP POST | LAN only, Mac firewall prompt once |
| Mac → Gmail | 465 | SMTP over TLS | app password |

## Things learned the hard way

- The first WiFi auth attempt after an ESP32 boot often fails; the second succeeds. Not a wrong password.
- macOS asks "allow incoming connections?" the first time a Python program opens a port. Click Allow or the phone gets nothing.
- iCloud Drive on the Mac wasn't syncing (stale since May 2025), so the phone→Mac photo path was rebuilt as a direct POST. Direct beats cloud-in-the-middle for a LAN feature anyway.
- The container this project is built from (Claude's cloud sandbox) can't reach the LAN; tests happen on the Mac or the Pi, or offline with stubs.

## Later

A Telegram bot (outbound HTTPS from the Mac, polling) is the plan for sending tasks from campus without opening any ports at home.
