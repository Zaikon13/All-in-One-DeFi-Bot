# DEPLOY — Railway (Web + Worker)

1) **Web service**
   - Source: αυτό το repo
   - Procfile: `web: uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}`
   - Variables: όπως στο RAILWAY.md (χωρίς secrets στο repo)

2) **Worker service**
   - New Service → from same repo
   - Start Command: `python -u worker.py`
   - Variables: ίδια βάση, + `WORKER_TICK_SEC` αν θέλεις (default 15)

3) **Telegram webhook**
   - `https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=$APP_URL/telegram/webhook`
   - Έλεγχος: `getWebhookInfo` → πρέπει `pending_update_count: 0`

4) **Logs health**
   - Web: `INFO ... Waiting for application startup`, POST /telegram/webhook 200
   - Worker: `Worker heartbeat ok`
