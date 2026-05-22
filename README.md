# All-in-One DeFi Bot

**Professional DeFi Telegram Bot** specialized for the **Cronos** ecosystem with real-time wallet monitoring, PnL analytics, smart alerts, and trading capabilities.

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

## Quick Start (Local)

```bash
git clone https://github.com/Zaikon13/All-in-One-DeFi-Bot.git
cd All-in-One-DeFi-Bot
pip install -r requirements.txt

# Run Web
uvicorn app:app --host 0.0.0.0 --port 8000

# Run Worker (in another terminal)
python -u worker.py
```

## Deployment

- **Platform**: Railway (3 services: bot, web-gpl6, worker)
- **See**: `DEPLOYMENT_SOP.md` for full details

## Documentation

- `docs/project-status.md` — Single Source of Truth
- `DEPLOYMENT_SOP.md` — Deployment guide
- `GROK_HEALTH.md` — Grok integration health

**Last Updated**: 2026-05-22