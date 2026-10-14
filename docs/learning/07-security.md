# 7. Security

Threat model: a small home project, not a bank. The goals are (1) nothing embarrassing or dangerous in a public repo, (2) a stranger on the WiFi can't drive the room, (3) the agent can't wreck the Mac, (4) no account gets banned.

## Secrets out of git

| Secret | Lives in | Used by |
|---|---|---|
| WiFi password, API encryption key, OTA password, web password | `secrets.yaml` (`!secret` in the YAML) | ESPHome |
| board web password | `board-password.txt` | server, Doctor |
| HA long-lived token | `ha-token.txt` | ears, bridge, Doctor |
| Anthropic API key | `anthropic-key.txt` | bridge → agent env |
| Gmail app password | `gmail-app-password.txt` | bridge email |
| bCourses token | `canvas-token.txt` | study puller |

`.gitignore` names every one. The Oct 14 lesson: the board YAML was committed with secrets inline for two weeks; the fix was moving them out **and squashing git history**, because a secret in an old commit is still a secret.

What to rotate if a secret leaks: web password and API key (edit `secrets.yaml`, flash, re-enter the key in HA); the HA token (make a new one, update the files); the Anthropic key (console); the Gmail app password (Google account). The WiFi password is the family's call.

## The agent's leash

- Working directory = its task folder; `acceptEdits` lets it edit there and nowhere else without a human.
- Tools beyond that are allow-listed: `WebFetch`, `WebSearch`, `Bash(curl:*)`. No shell, no other commands.
- Fixed PATH and env; the API key passed only to that process.
- 15-minute timeout, $20/month cap, every run logged.
- "Draft, don't send": the recruiting agent writes messages; it has no way to post them.

## The room

- Board web page behind basic auth; HUD behind a PIN; HA behind its own login.
- Webhooks and the photo drop are LAN-only. Nothing is port-forwarded.

## Account safety

No scraping, no bots on Instagram or LinkedIn, no logging in from code. Items enter through the iOS share sheet, one at a time, by a human. If Instagram refuses an anonymous download, the digest says so rather than working around it.
