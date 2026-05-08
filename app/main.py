# app/main.py
# Fixed: Real $ PnL + DexScreener + Grok AI + correct FastAPI imports
# Removed Covalent completely - using only Cronos Explorer

from __future__ import annotations

import os
import logging
from typing import Any, Dict, Optional
import httpx
from datetime import datetime, timedelta
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
# Daily PnL - Real $ PnL via Cronos Explorer + DexScreener + Grok AI
# ---------------------------------------------------------------------
async def get_daily_pnl() -> str:
    if not WALLET_ADDRESS:
        return "❌ WALLET_ADDRESS not configured."

    await send_telegram_message("📡 Fetching recent trades from Cronos explorer...", CHAT_ID)

    # Cronos Explorer API
    url = f"https://cronos.org/explorer/api?module=account&action=tokentx&address={WALLET_ADDRESS}&startblock=0&endblock=999999999&page=1&offset=100&sort=desc"

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logging.exception("Cronos Explorer error")
        return f"❌ Error fetching trades: {str(e)[:200]}"

    items = data.get("result", [])
    if not items:
        return "📅 No transactions found in the last 24h."

    cutoff = datetime.now() - timedelta(hours=24)
    trades = []
    total_pnl_usd = 0.0

    for tx in items:
        block_time = tx.get("timeStamp")
        if not block_time:
            continue
        tx_time = datetime.fromtimestamp(int(block_time))
        if tx_time < cutoff:
            continue

        symbol = tx.get("tokenSymbol", "UNKNOWN")
        amount = float(tx.get("value", 0)) / (10 ** int(tx.get("tokenDecimal", 18)))
        if abs(amount) < 0.0001:
            continue

        # Get price from DexScreener
        contract = tx.get("contractAddress")
        price_usd = 0.0
        if contract:
            try:
                ds_url = f"https://api.dexscreener.com/latest/dex/tokens/{contract}"
                async with httpx.AsyncClient(timeout=8) as ds:
                    ds_resp = await ds.get(ds_url)
                    pairs = ds_resp.json().get("pairs", [])
                    if pairs:
                        price_usd = float(pairs[0].get("priceUsd", 0) or 0)
            except:
                pass

        usd_value = abs(amount) * price_usd
        direction = "→" if tx.get("to") == WALLET_ADDRESS.lower() else "←"
        emoji = "🟢" if direction == "→" else "🔴"

        trades.append({
            "time": tx_time.strftime("%H:%M"),
            "symbol": symbol,
            "amount": amount,
            "usd": usd_value,
            "direction": direction,
            "emoji": emoji,
            "tx_hash": tx.get("hash", "")[:10] + "...",
            "link": f"https://cronos.org/explorer/tx/{tx.get('hash', '')}"
        })

        total_pnl_usd += usd_value if direction == "→" else -usd_value

    if not trades:
        return "📅 No trades in the last 24 hours."

    # Build report
    message = f"📊 **Daily PnL Report** — Last 24h\n"
    message += f"Wallet: `{WALLET_ADDRESS[:8]}...{WALLET_ADDRESS[-6:]}`\n\n"

    for t in trades[:12]:
        message += f"{t['emoji']} **{t['symbol']}** {t['direction']} {abs(t['amount']):,.4f} (${t['usd']:,.2f})\n"
        message += f"   {t['time']} | {t['tx_hash']}\n   🔗 [{t['tx_hash']}]({t['link']})\n\n"

    total_emoji = "🟢" if total_pnl_usd >= 0 else "🔴"
    message += f"**Total Daily PnL: {total_emoji} ${total_pnl_usd:,.2f}**\n\n"

    # Grok AI Analysis
    if GROK_API_KEY:
        try:
            prompt = f"Analyze these Cronos DeFi trades in Greek. Be short, useful and direct:\nTotal PnL: ${total_pnl_usd:.2f}\nTrades: {str([{'symbol':t['symbol'], 'usd':t['usd'], 'dir':t['direction']} for t in trades[:8]])}\nGive 3-4 short insights, risk notes and suggestions."
            async with httpx.AsyncClient(timeout=15) as g:
                r = await g.post(
                    "https://api.x.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROK_API_KEY}"},
                    json={
                        "model": "grok-beta",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.7
                    }
                )
                ai_comment = r.json()["choices"][0]["message"]["content"]
                message += f"🤖 **Grok AI Analysis**:\n{ai_comment}"
        except Exception as e:
            logging.exception("Grok AI error")
            message += "\n🤖 Grok AI (temporarily unavailable)"
    else:
        message += "\n🤖 Grok AI not configured."

    return message

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
    await send_telegram_message("✅ All-in-One-DeFi-Bot web is online.")

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

    # Handle /start command - robust version
    if text.startswith('/start'):
        welcome_msg = (
            "👋 **Καλώς ήρθες στο All-in-One-DeFi-Bot!**\n\n"
            "✅ `/daily_pnl` → Ημερήσιο PnL report\n"
            "✅ Worker + Web service online\n"
            "✅ Cronos Explorer + DexScreener\n\n"
            "Πληκτρολόγησε /daily_pnl για να δεις το report σου!"
        )
        await send_telegram_message(welcome_msg, chat_id)
        return JSONResponse({"ok": True})

    elif text in ["/daily_pnl", "/dailypnl"]:
        report = await get_daily_pnl()
        await send_telegram_message(report, chat_id)
    elif text:
        await send_telegram_message(f"Echo: {text}", chat_id)

    return JSONResponse({"ok": True})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
