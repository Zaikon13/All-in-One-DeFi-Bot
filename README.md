# All-in-One DeFi Bot

**Professional DeFi Telegram Bot** specialized for the **Cronos** ecosystem with real-time wallet monitoring, PnL analytics, multi-chain new-pool alerts and a paper-trading **simulation**. It monitors and reports only — it does not execute trades.

## Current Features

- Real-time wallet monitoring & transaction tracking
- Daily PnL reports via Telegram (`/daily_pnl`)
- Grok-powered AI analysis
- Automated GitHub Actions workflows (Sync Check, Health Check, Code Review)
- Modular Web + Worker architecture on Railway

## Live Services

- **Web**: https://bot-production-3d9c.up.railway.app
- **Telegram Bot**: [@AllInOneDeFiBot](https://t.me/AllInOneDeFiBot)

## GitHub Actions Workflows (All Clean)

| Workflow | Status | Description |
|----------|--------|-------------|
| Sync Check | ✅ Green | Full repo sync + uncommitted changes check |
| Health Check Report | ✅ Green | Railway monitoring + Grok analysis + auto Issue |
| Grok Code Review | ✅ Ready | Automated PR reviews with Grok-4.3 |

## Quick Start — standalone (no Railway needed)

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