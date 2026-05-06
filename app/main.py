# app/main.py
#Grock2

from __future__ import annotations

import os
import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import httpx
from datetime import datetime, timedelta

# ---------------------------------------------------------------------
# Config (από Env)
# ---------------------------------------------------------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # string OK
APP_URL = os.getenv("APP_URL")  # optional, για αναφορά στα logs
TZ = os.getenv("TZ", "UTC")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")
CRONOS_RPC_URL = os.getenv("CRONOS_RPC_URL")

# ---------------------------------------------------------------------
# Daily PnL Function - Improved Version
# ---------------------------------------------------------------------
async def get_daily_pnl() -> str:
    """Fetches recent token transfers (tokentx) and builds Daily PnL report."""
    if not WALLET_ADDRESS:
        return "❌ WALLET_ADDRESS not configured."

    await send_telegram_message("📡 Fetching recent trades from Cronos explorer...", CHAT_ID)

    # Last 24 hours
    now = datetime.now()
    since = now - timedelta(hours=24)
    start_timestamp = int(since.timestamp())

    # Use tokentx to catch DEX swaps and token transfers
    API_URL = "https://cronos.org/explorer/api"

    params = {
        "module": "account",
        "action": "tokentx",     # Important: tokentx instead of txlist
        "address": WALLET_ADDRESS,
        "startblock": 0,
        "endblock": 99999999,
        "page": 1,
        "offset": 100,
        "sort": "desc"
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(API_URL, params=params)
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        logging.exception("Explorer API error")
        return f"❌ Error fetching transactions:\n{str(e)[:500]}"

    if data.get("status") != "1" or not data.get("result"):
        return "📅 No token transfers found in the last 24 hours."

    trades = []
    total_pnl_approx = 0.0

    for tx in data["result"]:
        tx_time = int(tx.get("timeStamp", 0))
        if tx_time < start_timestamp:
            continue

        token = tx.get("tokenSymbol") or tx.get("symbol") or "UNKNOWN"
        value = float(tx.get("value", 0)) / (10 ** int(tx.get("tokenDecimal", 18)))
        tx_hash = tx.get("hash", "")
        from_addr = tx.get("from", "")
        to_addr = tx.get("to", "")
        method = "Swap" if "swap" in str(tx.get("functionName","")).lower() else "Transfer"

        # Direction
        direction = "→" if from_addr.lower() == WALLET_ADDRESS.lower() else "←"

        # Very basic PnL (can be improved with price data later)
        pnl = value * 0.1 if direction == "←" else -value * 0.1   # rough guess
        total_pnl_approx += pnl

        trades.append({
            "time": datetime.fromtimestamp(tx_time).strftime("%H:%M"),
            "token": token,
            "value": value,
            "direction": direction,
            "method": method,
            "tx_hash": tx_hash,
            "pnl": pnl
        })

    if not trades:
        return "📅 No trades executed in the last 24 hours."

    # Build message
    message = f"📊 **Daily PnL Report** — Last 24h\n"
    message += f"Wallet: `{WALLET_ADDRESS[:8]}...{WALLET_ADDRESS[-6:]}`\n\n"

    for t in trades[:15]:  # limit to avoid message too long
        emoji = "🟢" if t["pnl"] >= 0 else "🔴"
        message += f"{emoji} **{t['token']}** {t['direction']} {t['value']:.4f} {t['token']}\n"
        message += f"   {t['time']} | {t['method']}\n"
        if t['tx_hash']:
            short_hash = t['tx_hash'][:8] + "..."
            link = f"https://cronos.org/explorer/tx/{t['tx_hash']}"
            message += f"   🔗 [{short_hash}]({link})\n"
        message += f"   PnL ≈ **${t['pnl']:.2f}**\n\n"

    total_emoji = "🟢" if total_pnl_approx >= 0 else "🔴"
    message += f"**Total Daily PnL: {total_emoji} ${total_pnl_approx:.2f}**"

    return message

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
                json={"chat_id": int(cid), "text": text, "parse_mode": "Markdown"},
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
    try:
        payload = await req.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid json"}, status_code=400)

    message = (payload.get("message") or payload.get("edited_message")) or {}
    text = (message.get("text") or "").strip().lower()
    from_user = message.get("from") or {}
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id") or "")

    if CHAT_ID and chat_id and chat_id != str(CHAT_ID):
        return JSONResponse({"ok": True, "ignored": True})

    if text == "/start":
        status = "✅ All-in-One-DeFi-Bot web is online."
        await send_telegram_message(status)
    elif text == "/daily_pnl" or text == "/dailypnl":
        report = await get_daily_pnl()
        await send_telegram_message(report)
    elif text:
        await send_telegram_message(f"Echo: {text}")

    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------
# Health + GitHub routers
# ---------------------------------------------------------------------
try:
    from app.health import router as health_router
    app.include_router(health_router)
except Exception:
    pass

try:
    from app.github_webhook import router as gh_router
    app.include_router(gh_router)
    logging.info("✅ GitHub webhook router loaded")
except Exception as e:
    logging.warning("⚠️ GitHub webhook router not loaded: %s", e)
