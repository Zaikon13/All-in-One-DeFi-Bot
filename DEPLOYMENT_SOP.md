# 🚀 DEPLOYMENT SOP – All-in-One-DeFi-Bot

**Last Updated**: 22 Μαΐου 2026
**Repo**: Zaikon13/All-in-One-DeFi-Bot

## Current Architecture (3 Services)

| Service | Type | Start Command | Purpose | Status | Webhook |
|---------|------|---------------|---------|--------|---------|
| **bot** | Web | `uvicorn app.main:app` | Primary Telegram webhook + /daily_pnl | ✅ Online | Active |
| **web-gpl6** | Web | `uvicorn app.main:app` | Redundant (same code) | ✅ Online | Inactive |
| **worker** | Worker | `python -u worker.py` | Background jobs, DeFi logic, scheduler | ✅ Online | — |

**Important**: The **bot** service is the only one with the registered Telegram webhook.

## Railway Services

- **bot-production-3d9c** → Primary (Telegram webhook)
- **web-gpl6-production** → Redundant
- **worker** → Background tasks

## How to Redeploy

1. Push to `main` (or merge PR)
2. Railway auto-redeploys all services
3. Check logs of **bot** service for "All-in-One-DeFi-Bot started"
4. Verify webhook: `getWebhookInfo`

## Environment Variables (Required)

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `WALLET_ADDRESS`
- `GROK_API_KEY`
- `APP_URL` = `https://bot-production-3d9c.up.railway.app`

**Single Source of Truth**: `docs/project-status.md`