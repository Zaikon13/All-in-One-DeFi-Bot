# app/main.py - Main FastAPI Application

from fastapi import FastAPI, Request
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="All-in-One-DeFi-Bot")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Import new PnL calculator
try:
    from core.pnl_calculator import calculate_daily_pnl, format_pnl_report
except ImportError:
    calculate_daily_pnl = None
    format_pnl_report = None


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "All-in-One-DeFi-Bot"}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """Handle incoming Telegram updates"""
    data = await request.json()
    update = Update.de_json(data, None)

    if update.message and update.message.text:
        text = update.message.text.strip().lower()
        chat_id = update.message.chat.id

        if text == "/start":
            await send_message(chat_id, "🚀 Welcome to All-in-One-DeFi-Bot!\n\nAvailable commands:\n/daily_pnl - Today's PnL\n/balances - Wallet balances\n/wallet - Detailed wallet\n/grok-analyze - AI analysis")

        elif text in ["/daily_pnl", "/dailypnl"]:
            if calculate_daily_pnl:
                await send_message(chat_id, "🔄 Generating accurate Daily PnL report...")
                try:
                    pnl_data = calculate_daily_pnl()
                    report = format_pnl_report(pnl_data)
                    await send_message(chat_id, report)
                except Exception as e:
                    await send_message(chat_id, f"❌ Error: {str(e)}")
            else:
                await send_message(chat_id, "❌ PnL module not available.")

        elif text in ["/balances", "/wallet", "/bal"]:
            await send_message(chat_id, "💰 Fetching wallet balances...")
            # (existing wallet logic stays here)

        elif text == "/grok-analyze":
            await send_message(chat_id, "🤖 Analyzing your wallet with Grok...")
            # (existing grok logic stays here)

    return {"status": "ok"}


async def send_message(chat_id: int, text: str):
    """Send message to Telegram"""
    if not TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown"
            })
    except Exception as e:
        print(f"Telegram send error: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
