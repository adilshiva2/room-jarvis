# 5. Agents and cost

## Tiers (cheapest wins)

| Tier | Handles | Engine | Typical cost |
|---|---|---|---|
| 0 | lights, scenes, sensor questions, custom sentences | Home Assistant intents on the Pi | $0 |
| 1 | open questions | Claude Sonnet 5.5 through HA (max 300 output tokens, Jarvis persona) | ~$0.0025 |
| 2 | tasks | Claude agent on the Mac (`claude -p`) | $0.01 – $0.25 |

Prices (verified Oct 13): Sonnet 5.5 $2 / M input tokens, $10 / M output. Haiku 5.5 is 20× cheaper but was judged too weak for the persona and tasks. A $20/month limit at the console is the fuse.

## What a run costs and why

A digest of 3 reels cost ~20¢. Where it went: the agent reads three full transcripts plus the prompt (input tokens), reasons, writes a multi-section digest in two formats (output tokens), and runs several tool calls (each call re-sends context). Most of that is **fixed overhead per run**, not per reel — so 10 reels ≈ 40–50¢, not 70¢. Rule: batch.

Screenshots cost more than text per item (image input), so the recruiting digest is ~10–25¢ for a handful. Same rule.

## Keeping it cheap

- Transcribe locally (done). Tokens never see audio.
- Hard caps: 300 output tokens for conversation; 15-minute task timeout; console spend limit.
- Short, specific prompts with a required output shape — less wandering, fewer tool calls.
- Don't run a digest for one item.
- Prompt caching (automatic on the API for repeated system prompts) helps Tier 1 over time.

## Why an agent and not an API call

A single API call can summarize text. An **agent** can read files, look at images, fetch a page, write several files, move things around, and decide the order — the recruiting digest needs all of that. `claude -p` gives the agent loop (plan → tool → observe → repeat) for free; the bridge only supplies the sandbox, the prompt, and the contract for the result.

## Watching it

Anthropic Console → Usage shows spend by day. The bridge logs each run in `~/jarvis-tasks/logs/` with the agent's full output.
