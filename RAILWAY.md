# RAILWAY DEPLOYMENT - All-in-One-DeFi-Bot

**Last Updated:** 6 Ιουνίου 2026  
**Based on:** Live Railway Console inspection + `railway.toml`

## 1. Current Services

| Service      | Type   | Status              | Start Command                                      | Purpose                                      | Notes |
|--------------|--------|---------------------|----------------------------------------------------|----------------------------------------------|-------|
| **bot**      | Web    |  Online (Primary) | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` | Telegram Webhook + Commands                  | **Active Webhook** |
| **worker**   | Worker |  Online           | `python -u worker.py`                              | Background jobs (Dexscreener, alerts)        | - |

**Primary Service:** `bot`  
**Webhook URL:** `https://bot-production-3d9c.up.railway.app/telegram/webhook`

## 2. Telegram Bot Runtime

- **Mode:** Webhook (FastAPI)
- **Entry Point:** `app/main.py`
- **`telegram/handlers.py`:** Legacy polling code  **NOT used in production**
- All commands handled via `BackgroundTasks` in `app/main.py`
- Confirmed running process: `uvicorn app.main:app`

## 3. Background Worker (`worker.py`)

| Job                    | Interval   | Status  | Notes |
|------------------------|------------|---------|-------|
| Heartbeat              | Every 1h   | Active  | Telegram status messages |
| Dexscreener Polling    | Every 5min | Active  | New pair alerts |
| Wallet Monitoring      | Every 10min| Basic   | Needs improvement |

**Persistence:** Uses `data/known_pairs.json`. **No Railway Volume** mounted  data is lost on redeploys.

## 4. Live Environment Variables

| Variable                 | Status | Used By |
|--------------------------|--------|---------|
| `TELEGRAM_BOT_TOKEN`     | Set    | bot + worker |
| `TELEGRAM_CHAT_ID`       | Set    | bot + worker |
| `WALLET_ADDRESS`         | Set    | bot + worker |
| `GROK_API_KEY`           | Set    | core/grok_client.py |
| `ETHERSCAN_API`          | Set    | core/pnl_calculator.py |
| `APP_URL`                | Set    | Fallback |

## 5. Known Issues & Recommendations

| Issue                              | Severity | Recommendation |
|------------------------------------|----------|----------------|
| No persistent volume               | Medium   | Add Railway Volume at `/app/data` |
| `monitor_wallet()` is minimal      | Medium   | Improve in `worker.py` |
| Legacy `telegram/handlers.py`      | Low      | Can be archived later |

## 6. Deployment Info

- Builder: Dockerfile
- Restart Policy: ON_FAILURE (max 10 retries)
- Health endpoint: `GET /health`

**References**: `railway.toml`, `app/main.py`, `worker.py`, `GROK_COORDINATION.md`

**Last verified:** 6 Ιουνίου 2026 via live Railway Console