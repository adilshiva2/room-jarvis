# iPhone shortcuts

Three Shortcuts-app automations connect the phone to Jarvis. All three are one or two actions.

## 1. "Jarvis" — Hey Siri, Jarvis
Opens Home Assistant's Assist and listens, so "Hey Siri, Jarvis" then a command works with the phone on the desk.
- Actions: **Dictate Text** → **Assist Prompt** (Prompt = Dictated Text, pipeline = Jarvis) → **Speak Text** (the Assist result).
- Rename the shortcut to exactly **Jarvis** so Siri recognizes it.

## 2. "Reel to Jarvis" — share sheet → webhook
- ⓘ → **Show in Share Sheet** on.
- One action: **Get Contents of URL** → `http://192.168.0.213:8123/api/webhook/jarvis-reel-7g2k`, Method **POST**, Request Body **JSON**, one field: key `url`, value **Shortcut Input**.
- Use: Instagram → Share → Reel to Jarvis. The bridge prints "Reel saved (N waiting)". Free until you run the digest.

## 3. "Photo to Jarvis" — share sheet → the Mac
- ⓘ → **Show in Share Sheet** on.
- One action: **Get Contents of URL** → `http://Adils-MacBook-Air-2.local:8802/photo`, Method **POST**, Request Body **File** = **Shortcut Input**.
- Use: screenshot a job post / recruiter / flyer → Share → Photo to Jarvis. The bridge prints "Screenshot received".

## Gotchas
- The ⓘ button sits at the bottom of the editor and is hidden while the action picker is open — add the first action, dismiss the picker, then look for it.
- Home WiFi only. Both targets are LAN addresses.
- "Save File to iCloud Drive" was the first design for photos; the Mac's iCloud Drive doesn't sync, so it was replaced by the direct POST.
