# All-in-One-DeFi-Bot

DeFi assistant για Cronos (επεκτάσιμο σε άλλα chains):
- Real-time monitoring (wallet + Dexscreener)
- PnL / reports
- Telegram alerts
- Trading bot με εντολές από Telegram

## Γρήγορη εκτέλεση (τοπικά)
- Python 3.12
- `pip install -r requirements.txt`
- Ρύθμισε τα περιβάλλοντα: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `WALLET_ADDRESS`, `CRONOS_RPC_URL`, `TZ`

## Φάκελοι
- `app/` backend (FastAPI / scheduler / Telegram bridge)
- `core/` logic (wallet, pricing, reports)
- `telegram/` commands & formatters
- `scripts/` helpers
