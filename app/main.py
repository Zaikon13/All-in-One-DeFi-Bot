# app/main.py
# REVERTED + Grok AI for /daily_pnl

from __future__ import annotations

import os
import logging
from typing import Any, Dict, Optional
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
# Daily PnL - Grok AI version with safe fallback
# ---------------------------------------------------------------------
async def get_daily_pnl() -> str:
    """Daily PnL με Grok AI (fallback στην παλιά λίστα αν κάτι πάει στραβά)"""
    try:
        # 1. Παλιά λογική για raw transactions
        url = f"https://cronos.org/explorer/api?module=account&action=tokentx&address={WALLET_ADDRESS}&startblock=0&endblock=999999999&page=1&offset=200&sort=desc"

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        transactions = data.get("result", [])
        
        if not transactions:
            return "📭 Δεν βρέθηκαν συναλλαγές τις τελευταίες ημέρες."

        # 2. Δημιουργία prompt για το Grok
        raw_data = "\n".join([
            f"{tx['timeStamp']} | {tx.get('tokenSymbol','?')} | {float(tx.get('value',0)) / (10**int(tx.get('tokenDecimal',18))):,.4f}"
            for tx in transactions[:50]
        ])

        prompt = f"""
        Wallet: {WALLET_ADDRESS}
        Τελευταίες συναλλαγές:
        {raw_data}

        Δημιούργησε ένα σύντομο, επαγγελματικό και χρήσιμο Daily PnL report στα Ελληνικά.
        Εστίασε σε:
        - Συνολική εικόνα (πόσες συναλλαγές, ποια tokens κυριαρχούν)
        - Top tokens / μεγαλύτερες κινήσεις
        - Τυχόν ενδιαφέρουσες παρατηρήσεις
        Κράτα το φιλικό και άμεσο.
        """

        # 3. Κλήση Grok
        grok_report = await ask_grok(
            prompt,
            system_prompt="Είσαι επαγγελματίας Cronos DeFi analyst. Μίλα στα Ελληνικά, είσαι άμεσος και λίγο savage."
        )

        return f"📊 **Smart Daily PnL Report**\n\n{grok_report}"

    except Exception as e:
        logging.error(f"Error in get_daily_pnl: {e}")
        # Fallback στην παλιά απλή λίστα
        fallback = "⚠️ Grok δεν μπόρεσε να απαντήσει. Εδώ είναι η κλασική λίστα:\n\n"
        for tx in transactions[:20]:
            time_str = datetime.fromtimestamp(int(tx['timeStamp'])).strftime("%d/%m %H:%M")
            symbol = tx.get("tokenSymbol", "???")
            value = float(tx.get("value", 0)) / (10 ** int(tx.get("tokenDecimal", 18)))
            fallback += f"• {time_str} | {symbol} | {value:,.4f}\n"
        return fallback

# ---------------------------------------------------------------------
# Telegram Helpers (same as before)
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
# FastAPI App (same as before)
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
