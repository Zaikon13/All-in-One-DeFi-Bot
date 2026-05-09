# app/main.py
# Updated: Robust Grok AI for /daily_pnl with excellent fallback

from __future__ import annotations

import os
import logging
from typing import Any, Dict, Optional, List
import httpx
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Config
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")
GROK_API_KEY = os.getenv("GROK_API_KEY")


def build_raw_pnl_report(transactions: List[Dict], wallet: str) -> str:
    report = f"📊 **Daily PnL Report**\n\n"
    report += f"🔑 Wallet: `{wallet[:8]}...{wallet[-6:]}`\n"
    report += f"📦 {len(transactions)} recent transactions\n\n"

    for tx in transactions[:15]:
        try:
            time_str = datetime.fromtimestamp(int(tx.get('timeStamp', 0))).strftime('%d/%m %H:%M')
            symbol = tx.get('tokenSymbol', '???')
            decimals = int(tx.get('tokenDecimal', 18))
            value = float(tx.get('value', 0)) / (10 ** decimals)
            report += f"• {time_str} | {symbol} | {value:,.4f}\n"
        except:
            continue
    return report


async def call_grok_api(prompt: str) -> str:
    if not GROK_API_KEY:
        raise ValueError("No GROK_API_KEY")

    url = "https://api.x.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "grok-beta",
        "messages": [
            {"role": "system", "content": "You are an expert DeFi analyst. Give clear, actionable insights."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.6,
        "max_tokens": 700
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data['choices'][0]['message']['content'].strip()


async def analyze_with_grok(transactions: List[Dict], wallet: str) -> str:
    tx_lines = []
    for tx in transactions[:20]:
        try:
            time_str = datetime.fromtimestamp(int(tx.get('timeStamp', 0))).strftime('%d/%m %H:%M')
            symbol = tx.get('tokenSymbol', 'Unknown')
            value = float(tx.get('value', 0)) / (10 ** int(tx.get('tokenDecimal', 18)))
            tx_lines.append(f"{time_str} | {symbol} | {value:,.4f}")
        except:
            continue

    prompt = f"""Wallet: {wallet}

Recent trades (newest first):
{chr(10).join(tx_lines)}

Create a clean and insightful Daily PnL summary. Highlight key trades, total activity, and any patterns. Use markdown. Be concise."""

    return await call_grok_api(prompt)


async def get_daily_pnl() -> str:
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
            return "📭 No recent transactions found."

        # Try Grok AI
        if GROK_API_KEY:
            try:
                ai_report = await analyze_with_grok(transactions, WALLET_ADDRESS)
                return f"📊 **Grok AI Daily PnL Report**\n\n{ai_report}"
            except Exception as e:
                logging.warning(f"Grok AI failed: {str(e)[:100]}")

        # Safe fallback
        return build_raw_pnl_report(transactions, WALLET_ADDRESS)

    except Exception as e:
        logging.exception("get_daily_pnl error")
        return f"❌ Error: {str(e)[:100]}"


# Telegram Helpers (unchanged)
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
                json={"chat_id": int(cid), "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}
            )
    except:
        pass


# FastAPI App (simplified)
app = FastAPI(title="All-in-One-DeFi-Bot")

@app.on_event("startup")
async def _startup() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.info("✅ All-in-One-DeFi-Bot started")
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

    if text.startswith('/start'):
        await send_telegram_message("👋 **Welcome!** Type `/daily_pnl` for Grok AI report.", chat_id)
        return JSONResponse({"ok": True})

    elif text in ("/daily_pnl", "/dailypnl"):
        report = await get_daily_pnl()
        await send_telegram_message(report, chat_id)
    elif text:
        await send_telegram_message(f"Echo: {text}", chat_id)

    return JSONResponse({"ok": True})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
