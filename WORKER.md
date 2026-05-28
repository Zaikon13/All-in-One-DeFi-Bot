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
- ✅ Real new pair detection on Cronos with rich Telegram alerts (using DexScreener)
- ✅ Basic persistence for known pairs via `data/known_pairs.json`
  - Survives in-process restarts and local development restarts.
  - **Important Railway limitation**: The filesystem is ephemeral by default. Pairs will be lost on redeploys unless a Railway Volume is mounted (see TODO in worker.py).
- ✅ Periodic wallet balance monitoring (CRO + ERC-20 tokens) with change detection alerts
- ✅ Heartbeat messages (hourly)
- ✅ Basic Grok-enhanced `/daily_pnl` (via webhook in app/main.py calling core.pnl_calculator) with async-safe Covalent + timeout + fallback. (Note: EOD scheduling still pending; this is net-delta only, not full PnL.)

**Remaining Tasks:**
- Improved new pair filtering (liquidity/volume thresholds)
- Full EOD PnL report scheduling
- Better error handling and retry logic
- Integration with core modules for more advanced logic
- Railway Volume integration for true restart durability of known pairs
