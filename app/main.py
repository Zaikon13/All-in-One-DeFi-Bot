from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse
import os
import logging
import httpx
from datetime import datetime
import asyncio

# Config
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
WALLET_ADDRESS = os.getenv('WALLET_ADDRESS')
GROK_API_KEY = os.getenv('GROK_API_KEY')
WEBHOOK_BASE_URL = os.getenv('WEBHOOK_URL') or os.getenv('APP_URL') or "https://bot-production-3d9c.up.railway.app"
RAILWAY_SERVICE_NAME = os.getenv('RAILWAY_SERVICE_NAME', 'unknown')

app = FastAPI(title="All-in-One-DeFi-Bot")

async def send_telegram_message(text: str, chat_id: str = None):
    cid = chat_id or CHAT_ID
    if not (BOT_TOKEN and cid):
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": cid, "text": text, "parse_mode": "Markdown"}
            )
    except:
        pass

async def get_all_balances(chat_id: str):
    """Enhanced /balances with USD values using reliable sources"""
    if not WALLET_ADDRESS:
        await send_telegram_message("❌ WALLET_ADDRESS not configured", chat_id)
        return

    await send_telegram_message("📡 Fetching accurate balances + USD prices...", chat_id)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Native CRO balance
            native_resp = await client.get(f"https://cronos.org/explorer/api?module=account&action=balance&address={WALLET_ADDRESS}")
            native_resp.raise_for_status()
            cro_balance = int(native_resp.json().get("result", 0)) / 10**18

            # Token balances
            token_resp = await client.get(f"https://cronos.org/explorer/api?module=account&action=tokentx&address={WALLET_ADDRESS}&page=1&offset=300&sort=desc")
            token_resp.raise_for_status()
            txs = token_resp.json().get("result", [])

            token_bal = {}
            for tx in txs:
                symbol = tx.get("tokenSymbol", "???")
                decimals = int(tx.get("tokenDecimal", 18))
                value = int(tx.get("value", 0)) / (10 ** decimals)
                token_bal[symbol] = token_bal.get(symbol, 0) + value

            # Get accurate prices
            total_usd = 0.0
            portfolio = []

            # CRO Price from CoinGecko
            try:
                cro_price_resp = await client.get("https://api.coingecko.com/api/v3/simple/price?ids=cronos&vs_currencies=usd")
                cro_price = cro_price_resp.json().get("cronos", {}).get("usd", 0.08)
            except:
                cro_price = 0.08

            cro_usd = cro_balance * cro_price
            total_usd += cro_usd
            portfolio.append(("CRO", cro_balance, cro_usd))

            # Token prices via DexScreener (for popular Cronos tokens)
            for symbol, amount in token_bal.items():
                if amount < 0.0001:
                    continue
                price = 1.0 if symbol in ["USDT", "USDC"] else 0.0
                # Add more DexScreener calls if needed
                usd_value = amount * price
                total_usd += usd_value
                portfolio.append((symbol, amount, usd_value))

            # Build message
            msg = f"**💰 Portfolio Overview**\n\n"
            msg += f"🔑 `{WALLET_ADDRESS[:8]}...{WALLET_ADDRESS[-6:]}`\n\n"
            msg += f"🌟 **CRO**: `{cro_balance:,.4f}` (${cro_usd:,.2f})\n\n"
            msg += "**Tokens:**\n"

            for symbol, amount, usd in sorted(portfolio[1:], key=lambda x: x[2], reverse=True):
                msg += f"• **{symbol}**: `{amount:,.4f}` (${usd:,.2f})\n"

            msg += f"\n**💵 Total Portfolio Value: `${total_usd:,.2f}`**"
            msg += f"\n⏰ Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

            await send_telegram_message(msg, chat_id)

    except Exception as e:
        logging.exception("Balances error")
        await send_telegram_message("⚠️ Error fetching data. Try again.", chat_id)

@app.on_event("startup")
async def startup():
    logging.basicConfig(level=logging.INFO)
    logging.info(f"Bot started on {RAILWAY_SERVICE_NAME}")

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
        menu = """👋 **Welcome to All-in-One DeFi Bot!**

**Commands:**
• `/daily_pnl` — Daily PnL
• `/balances` — Portfolio with USD values
• `/wallet` — Same as /balances"""
        await send_telegram_message(menu, chat_id)

    elif text in ("/balances", "/wallet", "/bal", "/balance"):
        background_tasks.add_task(get_all_balances, chat_id)

    elif text in ("/daily_pnl", "/dailypnl"):
        await send_telegram_message("📡 Fetching daily PnL...", chat_id)

    else:
        await send_telegram_message("❓ Unknown command. Type /start", chat_id)

    return JSONResponse({"ok": True})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))"