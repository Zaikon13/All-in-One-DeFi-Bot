from fastapi import FastAPI, Request
import logging

app = FastAPI(title="All-in-One-DeFi-Bot Web")
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

@app.get('/health')
async def health():
    return {"status": "ok"}

@app.get('/')
async def root():
    return {"name": "All-in-One-DeFi-Bot"}

@app.post('/telegram/webhook')
async def telegram_webhook(req: Request):
    payload = await req.json()
    log.info("telegram update: %s", payload)
    return {"ok": True}
