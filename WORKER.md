# WORKER — Background Service

Start Command (Railway): `python -u worker.py`

Vars:
- WORKER_TICK_SEC (default 15)
- Μοιράζεται τα υπόλοιπα με το Web (βλ. RAILWAY.md).

Σκοπός:
- Wallet monitor, Dexscreener discovery, alerts, schedulers (EOD report).
- Τώρα: heartbeat/logging. Έτοιμο για επόμενα PRs.
