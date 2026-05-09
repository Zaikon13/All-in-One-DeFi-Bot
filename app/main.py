# app/main.py
# Clean version with Grok AI for /daily_pnl + safe fallback

from __future__ import annotations

import os
import logging
from typing import Any, Dict
from datetime import datetime
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Grok helper (inline for simplicity)
_grok_client = None

def get_grok_client():
    global _grok_client
    if _grok_client is None:
        api_key = os.getenv("GROK_API_KEY")
        if not api_key:
            raise ValueError("GROK_API_KEY not found")
        from xai_sdk import Client
        _grok_client = Client(api_key=api_key)
    return _grok_client

async def ask_grok(prompt: str, system_prompt: str = None) -> str:
    client = get_grok_client()
    from xai_sdk.chat import system, user
    chat = client.chat.create(model="grok-4.3")
    if system_prompt:
        chat.append(system(system_prompt))
    chat.append(user(prompt))
    response = await chat.sample()
    return response.text

# ---------------------------------------------------------------------
# Daily PnL - Simple + Grok AI
# ---------------------------------------------------------------------
async def get_daily_pnl() -> str:
    """Daily PnL με Grok (πολύ σύντομο prompt) + fallback"""
    try:
        # Get raw transactions
        url = f"https://cronos.org/explorer/api?module=account&action=tokentx&address={os.getenv('WALLET_ADDRESS')}&startblock=0&endblock=999999999&page=1&offset=150&sort=desc"

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        transactions = data.get("result", [])
        
        if not transactions:
            return "📭 Δεν βρέθηκαν συναλλαγές τις τελευταίες ημέρες."

        # Very short prompt for Grok
        raw_summary = "\n".join([
            f"{tx['timeStamp']} | {tx.get('tokenSymbol','?')} | {float(tx.get('value',0)) / (10**int(tx.get('tokenDecimal',18))):,.4f}"
            for tx in transactions[:30]
        ])

        prompt = f"Wallet: {os.getenv('WALLET_ADDRESS')}\nΤελευταίες συναλλαγές:\n{raw_summary}\n\nΔώσε σύντομο Daily PnL report στα Ελληνικά (2-5 προτάσεις)."

        # Call Grok
        grok_report = await ask_grok(
            prompt,
            system_prompt="Είσαι Cronos DeFi analyst. Μίλα στα Ελληνικά, σύντομα, καθαρά και άμεσα."
        )

        return f"📊 **Smart Daily PnL Report**\n\n{grok_report}"

    except Exception as e:
        logging.error(f"Grok failed in daily_pnl: {e}")
        # Fallback to classic list
        fallback = "⚠️ Grok δεν μπόρεσε να απαντήσει. Εδώ είναι η κλασική λίστα:\n\n"
        for tx in transactions[:20]:
            time_str = datetime.fromtimestamp(int(tx['timeStamp'])).strftime("%d/%m %H:%M")
            symbol = tx.get("tokenSymbol", "???"),
            value = float(tx.get("value", 0)) / (10 ** int(tx.get("tokenDecimal", 18)))
            fallback += f"• {time_str} | {symbol} | {value:,.4f}\n"
        return fallback

# ---------------------------------------------------------------------
# Rest of the file remains the same
# ---------------------------------------------------------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

app = FastAPI(title="All-in-One-DeFi-Bot")

@app.on_event("startup")
async def _startup() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.info("✅ All-in-One-DeFi-Bot started")

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
        await send_telegram_message("👋 Καλώς ήρθες! Πληκτρολόγησε /daily_pnl για το report σου.", chat_id)
    elif text == "/daily_pnl" or text == "/dailypnl":
        report = await get_daily_pnl()
        await send_telegram_message(report, chat_id)

    return JSONResponse({"ok": True})

def _bot_api(method: str) -> str:
    return f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

async def send_telegram_message(text: str, chat_id: str = None):
    cid = chat_id or CHAT_ID
    if not (BOT_TOKEN and cid):
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                _bot_api("sendMessage"),
                json={"chat_id": int(cid), "text": text, "parse_mode": "Markdown"}
            )
    except:
        pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
