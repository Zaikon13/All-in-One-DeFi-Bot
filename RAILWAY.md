# 🚂 RAILWAY DEPLOYMENT CONFIGURATION

**Last Updated:** 12 Μαΐου 2026

## Current Services (3 Active)

| Service     | Type   | Purpose                              | Status   | Notes |
|-------------|--------|--------------------------------------|----------|-------|
| **bot**     | Web    | Primary Telegram Webhook + /daily_pnl| ✅ Online | **Active Webhook** |
| **web-gpl6**| Web    | Redundant FastAPI instance           | ✅ Online | Can be disabled later |
| **worker**  | Worker | Background DeFi jobs (PnL, Dexscreener, alerts) | ✅ Online | Main logic pending full implementation |

**Primary Service:** `bot` (handles Telegram webhook)

**Webhook URL:** `https://bot-production-3d9c.up.railway.app/telegram/webhook`

**Key Environment Variables:** See `.env.example` and Railway Dashboard.

**Reference:** See `DEPLOYMENT_SOP.md` and `RAILWAY_CONFIG.md` for full details.