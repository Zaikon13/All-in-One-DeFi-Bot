# Telegram Bot Token Rotation Runbook

**Status: prepared 2026-07-17 — NOT yet executed. Nothing in this document changes
anything by sitting here. Use it the day you decide to rotate.**

## Why this document exists

The bot token has leaked into places we don't control (an unknown "ghost" Railway
project from November 2025 still sends messages with it). Rotating the token is the
one move that silences every rogue copy everywhere, forever. It was postponed because
a botched rotation in the past ("the 2023 webhook chaos") left the bot deaf for days.
This runbook makes that impossible: the whole thing is four steps, and every step has
a verification you can see with your own eyes.

## The one fact that makes this safe

**This bot does NOT set its own Telegram webhook on startup.** (Verified in code
2026-07-17: no `set_webhook` / `setWebhook` call exists in `app/`, `core/`, or
`worker.py`.) The webhook was configured manually once, long ago. That means:

- Redeploying with a new token does **not** fix the webhook by itself.
- After rotating, there is exactly **one manual call** to make (Step 4).
- If the bot is ever "deaf" after a rotation, it is ALWAYS this: the webhook is
  still bound to the old token's URL. Step 4 cures it in one line.

The webhook URL is tied to the TOKEN, not the domain: Telegram routes updates for
YOUR bot to whatever URL was registered *with that token*. A new token starts with
NO webhook at all until you register one.

## Before you start (5 minutes, read-only)

1. Have ready: BotFather chat open, Railway dashboard open on the project
   `All-in-One-DeFi-Bot` (the REAL one, project id `386cea3a…`), and a terminal.
2. Capture the current webhook so you know the target URL to re-register.
   In a terminal (uses the OLD token, read-only):

   ```
   curl "https://api.telegram.org/bot<OLD_TOKEN>/getWebhookInfo"
   ```

   Write down the `url` field. Expected:
   `https://bot-production-3d9c.up.railway.app/telegram/webhook`
   If it shows anything else, THAT unknown URL is where your messages have been
   routed — note it for the post-mortem, but proceed the same way.
3. Pick a quiet moment (the bot will be deaf for ~2–5 minutes mid-rotation).

## The rotation (4 steps)

**Step 1 — Revoke in BotFather.**
BotFather → `/mybots` → select the bot → **API Token** → **Revoke current token**.
BotFather immediately shows the NEW token. Copy it. From this second, every rogue
copy of the old token — including the ghost project — is dead. Your own services
are also dead until Step 3 finishes. That's expected.

**Step 2 — Update ONE Railway variable.**
Railway → project → **each service that has `TELEGRAM_BOT_TOKEN`** (worker, bot,
and web-GPl6 if it still exists) → Variables → replace `TELEGRAM_BOT_TOKEN` with
the new value. If the variable is defined once as a shared/project variable,
change it once there instead.

**Step 3 — Redeploy.**
Railway usually redeploys automatically when a variable changes. If not: each
service → ⋮ menu → **Redeploy**. Wait until all show SUCCESS. (The services only
READ the token; no code change is needed and none should be made.)

**Step 4 — Re-register the webhook (the step that was missed in 2023).**
One line in the terminal, with the NEW token and the URL from "Before you start":

```
curl "https://api.telegram.org/bot<NEW_TOKEN>/setWebhook?url=https://bot-production-3d9c.up.railway.app/telegram/webhook"
```

Expected reply: `{"ok":true,"result":true,"description":"Webhook was set"}`

## Verification checklist (2 minutes, in order)

- [ ] `curl "https://api.telegram.org/bot<NEW_TOKEN>/getWebhookInfo"` shows the
      right `url` and `"pending_update_count"` is a small number.
- [ ] Send `/start` to the bot in Telegram → menu appears.
- [ ] Send `/wallet` → balances arrive (or the honest "data source unavailable"
      warning — either proves the pipeline is alive end-to-end).
- [ ] Worker logs in Railway show a fresh heartbeat / `balance read:` line after
      the redeploy timestamp.
- [ ] THE PRIZE: the bare-format ghost alerts STOP appearing from this moment.
      If any old-format message arrives after rotation, it is not using this
      token — screenshot it, because that would be a different bot entirely.

## Rollback (if something is wrong)

There is no "rollback" to the old token (it is revoked, by design). But nothing
in this procedure can strand you: any problem is fixed by re-running Step 4
(webhook), or re-checking Step 2 (typo'd variable). The worst possible state is
"bot deaf for a few minutes" — never data loss, never on-chain risk.

## What this does NOT touch

- The Cronos Explorer API key (`CRONOS_EXPLORER_API_KEY`) — unchanged.
- The Railway project token — unchanged (pasted per session, never stored).
- Any code, any chat history, any wallet, any chain state.
