# app/main.py
# REVERTED: back to old cronos.org/explorer for /daily_pnl as requested

from __future__ import annotations

import os
import logging
from typing import Any, Dict, Optional
import httpx
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
APP_URL = os.getenv("APP_URL")
TZ = os.getenv("TZ", "UTC")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")
GROK_API_KEY = os.getenv("GROK_API_KEY")

# ---------------------------------------------------------------------
# Daily PnL - OLD VERSION with cronos.org/explorer
# ---------------------------------------------------------------------
async def get_daily_pnl() -> str:
    """Παλιά έκδοση με cronos.org/explorer (όπως ήταν πριν)"""
    if not WALLET_ADDRESS:
        return "❌ WALLET_ADDRESS not configured."

    await send_telegram_message("📡 Fetching recent trades from Cronos Explorer...", CHAT_ID)

    url = f"https://cronos.org/explorer/api?module=account&action=tokentx&address={WALLET_ADDRESS}&startblock=0&endblock=999999999&page=1&offset=200&sort=desc"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        transactions = data.get("result", [])
        
        if not transactions:
            return "📭 Δεν βρέθηκαν συναλλαγές τις τελευταίες ημέρες."

        report = f"📊 **Daily PnL Report**\n\n"
        report += f"🔑 Wallet: `{WALLET_ADDRESS[:8]}...{WALLET_ADDRESS[-6:]}`\n"
        report += f"📦 Βρέθηκαν {len(transactions)} συναλλαγές\n\n"

        for tx in transactions[:15]:
            time_str = datetime.fromtimestamp(int(tx["timeStamp"])).strftime("%d/%m %H:%M")
            symbol = tx.get("tokenSymbol", "???" )
            value = float(tx.get("value", 0)) / (10 ** int(tx.get("tokenDecimal", 18)))
            report += f"• {time_str} | {symbol} | {value:,.4f}\n"

        return report

    except httpx.ReadTimeout:
        return "⏳ Το Cronos Explorer αργεί. Δοκίμασε ξανά σε λίγα δευτερόλεπτα."
    except Exception as e:
        logging.exception("Error in get_daily_pnl")
        return f"❌ Σφάλμα: {str(e)[:150]}"

# ---------------------------------------------------------------------
# Telegram Helpers
# ---------------------------------------------------------------------
def _bot_api(method: str) -> str:
    if not BOT_TOKEN:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")
    return f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

async def send_telegram_message(text: str, chat_id: Optional[str] = None) -> None:
    cid = chat_id or CHAT_ID
    if not (BOT_TOKEN and cid):
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                _bot_api("sendMessage"),
                json={"chat_id": int(cid), "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True},
            )
    except:
        pass

# ---------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------
app = FastAPI(title="All-in-One-DeFi-Bot")

@app.on_event("startup")
async def _startup() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.info("✅ All-in-One-DeFi-Bot web service started")
    await send_telegram_message("✅ All-in-One-DeFi-Bot is online.")

@app.get("/")
@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"ok": True, "name": "All-in-One-DeFi-Bot"}

@app.post("/telegram/webhook")
async def telegram_webhook(req: Request) -> JSONResponse:
    try:
        payload = await req.json()
    except:
        return JSONResponse({"ok": False}, status_code=400)

    message = (payload.get("message") or payload.get("edited_message")) or {}
    text = (message.get("text") or "").strip().lower()
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id") or "")

    logging.info(f"Received command: '{text}' from chat {chat_id}")

    if text.startswith('/start'):
        welcome_msg = (
            "👋 **Καλώς ήρθες στο All-in-One-DeFi-Bot!**\n\n"
            "✅ `/daily_pnl` → Ημερήσιο PnL report\n"
            "✅ Worker + Bot service online\n\n"
            "Πληκτρολόγησε /daily_pnl για να δεις το report σου!"
        )
        await send_telegram_message(welcome_msg, chat_id)
        return JSONResponse({"ok": True})

    elif text == "/daily_pnl" or text == "/dailypnl":
        report = await get_daily_pnl()
        await send_telegram_message(report, chat_id)
    elif text:
        await send_telegram_message(f"Echo: {text}", chat_id)

    return JSONResponse({"ok": True})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
