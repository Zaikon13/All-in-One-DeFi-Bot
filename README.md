# All-in-One-DeFi-Bot SPOT-v2 infra

DeFi assistant για Cronos (επεκτάσιμο σε άλλα chains):
- Real-time monitoring (wallet + Dexscreener)
- PnL / reports
- Telegram alerts
- Trading bot με εντολές από Telegram

## Services (Railway)
- **Web**: FastAPI (`/health`, `/telegram/webhook`)
- **Worker**: background loops (wallet monitor, discovery, alerts, schedulers)
  
## Γρήγορη εκτέλεση (τοπικά)
- Python 3.12
- `pip install -r requirements.txt`
- Ρύθμισε τα περιβάλλοντα: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `WALLET_ADDRESS`, `CRONOS_RPC_URL`, `TZ`

## Φάκελοι
- `app/` backend (FastAPI / scheduler / Telegram bridge)
- `core/` logic (wallet, pricing, reports)
- `telegram/` commands & formatters
- `scripts/` helpers

## Quick Start
1) Προσθέτεις τα αρχεία του SPOT στο repo.
2) GitHub → Actions **Secrets/Variables** (χωρίς secrets στο repo).
3) Railway:
   - Service A (Web): Procfile
   - Service B (Worker): Start Command `python -u worker.py`
4) Set Telegram webhook:
   `https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=$APP_URL/telegram/webhook`

## Status
SPOT-v2 δίνει **σταθερή υποδομή**. Οι λειτουργίες (handlers, monitors, alerts) μπαίνουν με μικρά PRs.
