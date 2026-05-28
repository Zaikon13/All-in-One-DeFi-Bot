# WORKER — Background Service

Start Command (Railway): `python -u worker.py`

Vars:
- WORKER_TICK_SEC (default 15)
- Μοιράζεται τα υπόλοιπα με το Web (βλ. RAILWAY.md).

Σκοπός:
- Real-time wallet balance monitoring with change alerts
- Dexscreener new pair discovery + Telegram alerts for new Cronos tokens
- Heartbeat + background jobs

**Current Features (Implemented):**
- ✅ New pair detection on Cronos with rich alerts
- ✅ Periodic wallet monitoring (CRO + ERC-20 tokens)
- ✅ Heartbeat messages
- In-memory pair tracking (resets on restart)
