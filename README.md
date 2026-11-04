# All-in-One DeFi Bot

**Professional DeFi Telegram Bot** specialized for the **Cronos** ecosystem with wallet monitoring, daily activity reports, multi-chain new-pool alerts and a paper-trading **simulation**. It monitors and reports only — it does not execute trades.

## What it does

- `/wallet` — Cronos wallet balances with USD values (Cronos Explorer + Dexscreener)
- `/daily_pnl` — the day's wallet activity: net tokens in − out per token (this is
  *not* realized profit/loss — there is no cost basis), plus an optional AI note
- `/analyze` — Claude's plain-language read of recent balances and transfers
- `/signals` + alerts — new pools on Cronos / Solana / Sui (GeckoTerminal), scored 0-100
- `/paper` — paper-trading **simulation** of the scanner's 🔥 picks (no real money)
- Portfolio-move alerts on held tokens (≥10% move) and a daily scanner digest

## Status (2026-11-04)

- Hosting on Railway is paused, so the hosted bot (and its webhook URL) is down.
- `run_local.py` (below) runs everything in one process anywhere, without Railway.
- Full audit of errors and inconsistencies: `reviews/2026-11-04-full-audit.md`.

## CI

| Workflow | What it does |
|----------|--------------|
| CI (`ci.yml`) | import smoke test + pytest — the only gating check |
| Claude Code Review | advisory PR review (needs `ANTHROPIC_API_KEY` secret) |
| Claude Health Check | manual only — pings the hosted bot, opens at most one issue |
| Sync Check / Dependency Check / Deploy validation | informational |

## Quick Start — standalone (no Railway needed)

**Easiest (Windows):**
1. Download the ZIP of this branch and unzip it.
2. Double-click **`start_bot.bat`**.

It installs what it needs, asks once for your bot token (@BotFather → your bot → API Token),
finds your chat id by itself when you press Start in Telegram, messages you, and runs the bot.
On macOS/Linux use `./start_bot.sh`. Settings stay in the local `.env`, which is never uploaded.

Manual way:

`run_local.py` runs the bot **and** the worker in one process. No public URL, no
webhook, no volume to rent: Telegram is reached by long-polling and state lives
in `./data/`.

```bash
git clone https://github.com/Zaikon13/All-in-One-DeFi-Bot.git
cd All-in-One-DeFi-Bot
pip install -r requirements.txt
cp .env.example .env        # fill in what you have (see below)

python run_local.py --selftest   # run every command once, replies printed here, then exit
python run_local.py --console    # full bot + worker; type /wallet, /signals, /paper ... replies print here
python run_local.py              # real Telegram (polling) — needs TELEGRAM_BOT_TOKEN
```

What each feature needs:

| Feature | Needs |
|---|---|
| `/signals`, new-pool alerts, `/paper` simulation | nothing (keyless GeckoTerminal) |
| `/wallet`, portfolio-move alerts | `WALLET_ADDRESS`, `CRONOS_EXPLORER_API_KEY` |
| `/daily_pnl` | the above (+ `ANTHROPIC_API_KEY` for the AI insight) |
| `/analyze` | the above + `ANTHROPIC_API_KEY` |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (also the allow-list of who may talk to the bot) |

**Telegram token safety:** if the token already has a webhook (it is served by
another bot/service), the runner **refuses to start** rather than steal it. Use a
**new** bot from @BotFather, or pass `--take-over-webhook` deliberately.

Without a token (or with `--console`) nothing is sent to Telegram — every message
is printed to the terminal instead.

### Classic split (Railway: web + worker)

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000   # web (webhook)
python -u worker.py                               # worker
```

## Deployment

- **Platform**: Railway (3 services: bot, web-gpl6, worker)
- **See**: `DEPLOYMENT_SOP.md` for full details

## Documentation

- `docs/project-status.md` — Single Source of Truth
- `DEPLOYMENT_SOP.md` — Deployment guide
- `GROK_HEALTH.md` — Grok integration health

**Last Updated**: 2026-05-22