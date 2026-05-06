# app/main.py
# Updated with Real $ PnL via DexScreener + Grok AI Analysis

from __future__ import annotations

import os
import logging
from typing import Any, Dict, Optional
import httpx
from datetime import datetime, timedelta

# ---------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
APP_URL = os.getenv("APP_URL")
TZ = os.getenv("TZ", "UTC")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")
COVA_API_KEY = os.getenv("COVA_API_KEY") or "cqt_rQyD6PqwPyGkVvmWhBbyXWx9PxcD"
GROK_API_KEY = os.getenv("GROK_API_KEY")

# ---------------------------------------------------------------------
# Daily PnL - Real $ PnL + DexScreener + Grok AI
# ---------------------------------------------------------------------
async def get_daily_pnl() -> str:
    if not WALLET_ADDRESS:
        return "❌ WALLET_ADDRESS not configured."

    await send_telegram_message("📡 Fetching trades + real prices from DexScreener...", CHAT_ID)

    # Covalent API (Cronos chain = 25)
    url = f"https://api.covalenthq.com/v1/25/address/{WALLET_ADDRESS}/transactions_v2/"
    params = {"key": COVA_API_KEY, "page-size": 200}

    try:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logging.exception("Covalent error")
        return f"❌ Error fetching trades: {str(e)[:200]}"

    items = data.get("data", {}).get("items", [])
    if not items:
        return "📅 No transactions found."

    cutoff = datetime.now() - timedelta(hours=24)
    trades = []
    total_pnl_usd = 0.0

    for tx in items:
        tx_time = datetime.fromtimestamp(tx.get("block_signed_at"))
        if tx_time < cutoff:
            continue

        for transfer in tx.get("transfers", []):
            token = transfer.get("token", {})
            symbol = token.get("symbol") or "UNKNOWN"
            contract = token.get("contract_address")
            decimals = int(token.get("decimals", 18))
            delta = float(transfer.get("delta", 0))
            amount = delta / (10 ** decimals)
            if abs(amount) < 0.0001:
                continue

            # DexScreener price
            price_usd = 0.0
            if contract:
                try:
                    ds_url = f"https://api.dexscreener.com/latest/dex/tokens/{contract}"
                    async with httpx.AsyncClient(timeout=10) as ds:
                        ds_resp = await ds.get(ds_url)
                        pairs = ds_resp.json().get("pairs", [])
                        if pairs and isinstance(pairs, list):
                            price_usd = float(pairs[0].get("priceUsd", 0) or 0)
                except:
                    pass

            usd_value = abs(amount) * price_usd
            direction = "→" if delta > 0 else "←"
            emoji = "🟢" if direction == "→" else "🔴"

            trades.append({
                "time": tx_time.strftime("%H:%M"),
                "symbol": symbol,
                "amount": amount,
                "usd": usd_value,
                "direction": direction,
                "emoji": emoji,
                "tx_hash": tx.get("tx_hash", "")[:10] + "...",
                "link": f"https://cronos.org/explorer/tx/{tx.get('tx_hash', '')}"
            })

            total_pnl_usd += usd_value if direction == "→" else -usd_value

    if not trades:
        return "📅 No trades in the last 24 hours."

    # Build message
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
            prompt = f"Analyze these Cronos trades in Greek (short & useful):\nTotal PnL: ${total_pnl_usd:.2f}\nTrades: {str([{'symbol':t['symbol'], 'usd':t['usd'], 'dir':t['direction']} for t in trades[:8]])}\nGive insights, risk notes and suggestions."
            async with httpx.AsyncClient(timeout=15) as g:
                r = await g.post(
                    "https://api.x.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROK_API_KEY}"},
                    json={
                        "model": "grok-4.3",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.75
                    }
                )
                ai_comment = r.json()["choices"][0]["message"]["content"]
                message += f"🤖 **Grok AI Analysis**:\n{ai_comment}"
        except Exception as e:
            message += "\n🤖 Grok AI (temporarily unavailable)"
    else:
        message += "\n🤖 Grok AI not configured."

    return message

# ---------------------------------------------------------------------
# Helpers (kept unchanged)
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
                json={"chat_id": int(cid), "text": text, "parse_mode": "Markdown"},
            )
    except:
        pass

# FastAPI app (kept)
app = FastAPI(title="All-in-One-DeFi-Bot")

@app.on_event("startup")
async def _startup() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting Web service")
    await send_telegram_message("✅ All-in-One-DeFi-Bot web is online.")

@app.get("/")
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

    if text == "/start":
        await send_telegram_message("✅ All-in-One-DeFi-Bot web is online.")
    elif text in ["/daily_pnl", "/dailypnl"]:
        report = await get_daily_pnl()
        await send_telegram_message(report)
    elif text:
        await send_telegram_message(f"Echo: {text}")

    return JSONResponse({"ok": True})
