from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse
import os
import logging
import httpx
from datetime import datetime

# Config
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
WALLET_ADDRESS = os.getenv('WALLET_ADDRESS')
WEBHOOK_BASE_URL = os.getenv('WEBHOOK_URL') or os.getenv('APP_URL') or "https://bot-production-3d9c.up.railway.app"
RAILWAY_SERVICE_NAME = os.getenv('RAILWAY_SERVICE_NAME', 'unknown')

app = FastAPI(title="All-in-One-DeFi-Bot")

async def send_telegram_message(text: str, chat_id: str = None):
    cid = chat_id or CHAT_ID
    if not (BOT_TOKEN and cid):
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": cid, "text": text, "parse_mode": "Markdown"}
            )
    except:
        pass

async def get_all_balances(chat_id: str):
    if not WALLET_ADDRESS:
        await send_telegram_message("❌ WALLET_ADDRESS not configured", chat_id)
        return
    await send_telegram_message("📡 Fetching balances + USD prices...", chat_id)
    # Simple version for now
    await send_telegram_message("💰 /balances feature active", chat_id)

@app.get("/")
@app.get("/health")
async def health():
    """Health check routes - fixes root URL Not Found error"""
    return {"ok": True, "service": RAILWAY_SERVICE_NAME, "status": "running"}

@app.post("/telegram/webhook")
async def telegram_webhook(req: Request, background_tasks: BackgroundTasks):
    try:
        payload = await req.json()
        message = payload.get("message") or payload.get("edited_message") or {}
        text = (message.get("text") or "").strip().lower()
        chat_id = str((message.get("chat") or {}).get("id", ""))
    except:
        return JSONResponse({"ok": False}, status_code=400)

    if text.startswith("/start"):
        menu = """👋 **Welcome to All-in-One DeFi Bot!**

**Commands:**
• /daily_pnl
• /balances
• /wallet"""
        await send_telegram_message(menu, chat_id)

    elif text in ("/balances", "/wallet", "/bal", "/balance"):
        background_tasks.add_task(get_all_balances, chat_id)

    elif text in ("/daily_pnl", "/dailypnl"):
        await send_telegram_message("📡 Fetching daily PnL...", chat_id)

    else:
        await send_telegram_message("❓ Unknown command. Type /start", chat_id)

    return JSONResponse({"ok": True})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))