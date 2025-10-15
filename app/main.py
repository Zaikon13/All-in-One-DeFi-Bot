# app/main.py
from __future__ import annotations

import os
import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import httpx

# ---------------------------------------------------------------------
# Config (από Env)
# ---------------------------------------------------------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # string OK
APP_URL = os.getenv("APP_URL")  # optional, για αναφορά στα logs
TZ = os.getenv("TZ", "UTC")

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _bot_api(method: str) -> str:
    if not BOT_TOKEN:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")
    return f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

async def send_telegram_message(text: str, chat_id: Optional[str] = None) -> None:
    """Απλό helper για αποστολή μηνυμάτων."""
    cid = chat_id or CHAT_ID
    if not (BOT_TOKEN and cid):
        logging.warning("Skipping Telegram send (missing token or chat id)")
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                _bot_api("sendMessage"),
                json={"chat_id": int(cid), "text": text},
            )
    except Exception as e:
        logging.exception("Telegram send failed: %s", e)

# ---------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------
app = FastAPI(title="All-in-One-DeFi-Bot")

@app.on_event("startup")
async def _startup() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting Web service (TZ=%s, APP_URL=%s)", TZ, APP_URL)
    await send_telegram_message("✅ All-in-One-DeFi-Bot web is online.")

@app.get("/")
async def health() -> Dict[str, Any]:
    return {"ok": True, "name": "All-in-One-DeFi-Bot", "webhook": "/telegram/webhook"}

@app.post("/telegram/webhook")
async def telegram_webhook(req: Request) -> JSONResponse:
    """
    Λαμβάνει Telegram Update (JSON).
    Χειρίζεται απλά το /start και echo για δοκιμή.
    Επιτρέπει μόνο το configured CHAT_ID (προστασία).
    """
    try:
        payload = await req.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid json"}, status_code=400)

    message = (payload.get("message") or payload.get("edited_message")) or {}
    text = (message.get("text") or "").strip()
    from_user = message.get("from") or {}
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id") or "")

    # Απλή ασφάλεια: αν έχουμε ορισμένο CHAT_ID, αγνοούμε άλλα chats
    if CHAT_ID and chat_id and chat_id != str(CHAT_ID):
        # Optionally: ενημέρωσε ευγενικά τον άγνωστο χρήστη
        return JSONResponse({"ok": True, "ignored": True})

    if text.lower().startswith("/start"):
        await send_telegram_message("👋 Bot ready! Δοκίμασε να μου γράψεις κάτι για echo.")
    elif text:
        # echo
        await send_telegram_message(f"Echo: {text}")

    return JSONResponse({"ok": True})
