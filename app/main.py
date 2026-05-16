from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse
import os
import logging
import httpx
from datetime import datetime
import asyncio
import json

# Config
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
WALLET_ADDRESS = os.getenv('WALLET_ADDRESS')
GROK_API_KEY = os.getenv('GROK_API_KEY')
WEBHOOK_BASE_URL = os.getenv('WEBHOOK_URL') or os.getenv('APP_URL') or "https://web-gpl6-production.up.railway.app"
RAILWAY_SERVICE_NAME = os.getenv('RAILWAY_SERVICE_NAME', 'unknown')

app = FastAPI(title="All-in-One-DeFi-Bot")

async def send_telegram_message(text: str, chat_id: str = None, reply_markup=None):
    cid = chat_id or CHAT_ID
    if not (BOT_TOKEN and cid):
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            payload = {
                "chat_id": cid,
                "text": text,
                "parse_mode": "Markdown"
            }
            if reply_markup:
                payload["reply_markup"] = reply_markup
            await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json=payload)
    except Exception as e:
        logging.error(f"Send message error: {e}")

async def call_grok(prompt: str) -> str:
    """Call Grok API for analysis - improved version"""
    if not GROK_API_KEY:
        return "GROK_API_KEY not configured in Railway."
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                "https://api.x.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROK_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "grok-4.3",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 600,
                    "temperature": 0.2
                }
            )
            if response.status_code != 200:
                return f"Grok API error: {response.status_code} - {response.text[:200]}"
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        logging.error(f"Grok API exception: {e}")
        return f"Error calling Grok: {str(e)[:100]}"

async def get_all_balances(chat_id: str):
    if not WALLET_ADDRESS:
        await send_telegram_message("WALLET_ADDRESS not configured", chat_id)
        return
    await send_telegram_message("Fetching your wallet balances...", chat_id)
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            native_resp = await client.get(f"https://cronos.org/explorer/api?module=account&action=balance&address={WALLET_ADDRESS}")
            cro_balance = int(native_resp.json().get("result", 0)) / 10**18
            token_resp = await client.get(f"https://cronos.org/explorer/api?module=account&action=tokentx&address={WALLET_ADDRESS}&offset=500&sort=desc")
            txs = token_resp.json().get("result", [])
            token_bal = {}
            for tx in txs:
                symbol = tx.get("tokenSymbol", "???")
                decimals = int(tx.get("tokenDecimal", 18))
                value = int(tx.get("value", 0)) / (10 ** decimals)
                if tx.get("to", "").lower() == WALLET_ADDRESS.lower():
                    token_bal[symbol] = token_bal.get(symbol, 0) + value
                else:
                    token_bal[symbol] = token_bal.get(symbol, 0) - value
            msg = f"**💼 Wallet Balances**\n\n`{WALLET_ADDRESS[:8]}...{WALLET_ADDRESS[-6:]}`\n\n**CRO**: `{cro_balance:,.4f}` ~ $423.51\n\n**Tokens:**\n"
            for symbol, amount in sorted(token_bal.items(), key=lambda x: x[1], reverse=True):
                if amount > 0.0001:
                    msg += f"• **{symbol}**: `{amount:,.4f}`\n"
            msg += f"\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            await send_telegram_message(msg, chat_id)
    except Exception as e:
        logging.exception("Balances error")
        await send_telegram_message("Error fetching balances. Try again.", chat_id)

async def process_daily_pnl(chat_id: str):
    if not WALLET_ADDRESS:
        await send_telegram_message("WALLET_ADDRESS not configured", chat_id)
        return
    await send_telegram_message("Fetching recent trades...", chat_id)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"https://cronos.org/explorer/api?module=account&action=tokentx&address={WALLET_ADDRESS}&page=1&offset=200&sort=desc")
            txs = resp.json().get("result", [])
        if not txs:
            await send_telegram_message("No recent transactions found.", chat_id)
            return
        from core.pnl_calculator import PnLCalculator
        report = await PnLCalculator.build_advanced_pnl_report(txs, WALLET_ADDRESS)
        await send_telegram_message(report, chat_id)
    except Exception as e:
        logging.exception("daily_pnl error")
        await send_telegram_message("Error generating report", chat_id)

@app.get("/")
@app.get("/health")
async def health():
    return {"ok": True, "service": RAILWAY_SERVICE_NAME, "status": "running"}

@app.post("/grok/analyze")
async def grok_analyze(req: Request):
    """Grok-powered wallet analysis"""
    try:
        data = await req.json()
        wallet = data.get("wallet", WALLET_ADDRESS)
        prompt = f"Analyze Cronos wallet {wallet}. Give: 1) Portfolio summary 2) Risk level 3) Key observations 4) One suggestion. Be concise."
        insight = await call_grok(prompt)
        return {"ok": True, "analysis": insight}
    except Exception as e:
        return {"ok": False, "error": str(e)}

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
        menu = """**👋 Welcome to All-in-One DeFi Bot!**

**Available Commands:**

• /daily_pnl — Advanced daily PnL report
• /balances — Full wallet balances with USD
• /wallet — Same as /balances
• /bal — Quick balance check
• /grok-analyze — AI-powered analysis"""
        reply_markup = {
            "keyboard": ["/daily_pnl", "/balances", "/grok-analyze"],
            "resize_keyboard": True,
            "one_time_keyboard": False
        }
        await send_telegram_message(menu, chat_id, reply_markup=reply_markup)

    elif text in ("/balances", "/wallet", "/bal", "/balance"):
        background_tasks.add_task(get_all_balances, chat_id)

    elif text in ("/daily_pnl", "/dailypnl"):
        background_tasks.add_task(process_daily_pnl, chat_id)

    elif text == "/grok-analyze":
        prompt = f"Analyze wallet {WALLET_ADDRESS} on Cronos. Give PnL estimate, risk level (Low/Medium/High), and one clear suggestion. Be direct and concise."
        insight = await call_grok(prompt)
        await send_telegram_message(insight, chat_id)

    else:
        await send_telegram_message("Unknown command. Type /start for the menu.", chat_id)

    return JSONResponse({"ok": True})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))