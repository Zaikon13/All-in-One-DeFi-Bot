# app/main.py
# Fixed multi-service webhook conflict

from __future__ import annotations

import os
import logging
import asyncio
from typing import Any, Dict, List
from datetime import datetime
import httpx
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse

# Config
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
WALLET_ADDRESS = os.getenv('WALLET_ADDRESS')

# Force correct bot URL + service isolation
WEBHOOK_BASE_URL = (os.getenv('WEBHOOK_URL') or os.getenv('APP_URL') or "https://bot-production-3d9c.up.railway.app")
RAILWAY_SERVICE_NAME = os.getenv('RAILWAY_SERVICE_NAME', 'unknown')


def build_pnl_report(transactions: List[Dict], wallet: str) -> str:
    report = f"📊 **Daily PnL Report**\n\n"
    report += f"🔑 Wallet: `{wallet[:8]}...{wallet[-6:]}`\n"
    report += f"📦 {len(transactions)} recent transactions\n\n"

    for tx in transactions[:20]:
        try:
            time_str = datetime.fromtimestamp(int(tx.get('timeStamp', 0))).strftime('%d/%m %H:%M')
            symbol = tx.get('tokenSymbol', '???')
            decimals = int(tx.get('tokenDecimal', 18))
            value = float(tx.get('value', 0)) / (10 ** decimals)
            report += f"• {time_str} | {symbol} | {value:,.4f}\n"
        except:
            continue
    return report


async def process_daily_pnl(chat_id: str):
    if not WALLET_ADDRESS:
        await send_telegram_message('❌ WALLET_ADDRESS not configured.', chat_id)
        return

    await send_telegram_message('📡 Fetching recent trades from Cronos Explorer...', chat_id)

    url = f'https://cronos.org/explorer/api?module=account&action=tokentx&address={WALLET_ADDRESS}&startblock=0&endblock=999999999&page=1&offset=200&sort=desc'

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        transactions = data.get('result', [])

        if not transactions:
            await send_telegram_message('📭 No recent transactions found.', chat_id)
            return

        report = build_pnl_report(transactions, WALLET_ADDRESS)
        await send_telegram_message(report, chat_id)

    except Exception as e:
        logging.exception('get_daily_pnl error')
        await send_telegram_message('⚠️ Cronos Explorer temporarily unavailable. Please try again in a few seconds.', chat_id)


def _bot_api(method: str) -> str:
    if not BOT_TOKEN:
        raise RuntimeError('Missing TELEGRAM_BOT_TOKEN')
    return f'https://api.telegram.org/bot{BOT_TOKEN}/{method}'


async def send_telegram_message(text: str, chat_id: str = None) -> None:
    cid = chat_id or CHAT_ID
    if not (BOT_TOKEN and cid):
        return
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            await client.post(
                _bot_api('sendMessage'),
                json={
                    'chat_id': int(cid),
                    'text': text,
                    'parse_mode': 'Markdown',
                    'disable_web_page_preview': True
                }
            )
    except:
        pass


async def delete_webhook() -> None:
    """Delete current webhook for clean setup"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(_bot_api('deleteWebhook'))
            logging.info('🗑️ Old Telegram webhook deleted')
    except Exception as e:
        logging.warning(f'Failed to delete webhook: {e}')


async def set_webhook(webhook_url: str) -> None:
    """Set new Telegram webhook"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _bot_api('setWebhook'),
                json={
                    'url': webhook_url,
                    'allowed_updates': ['message', 'edited_message'],
                    'drop_pending_updates': True
                }
            )
            if resp.status_code == 200:
                logging.info(f'✅ Telegram webhook successfully set to: {webhook_url}')
            else:
                logging.error(f'Failed to set webhook. Status: {resp.status_code} - {resp.text}')
    except Exception as e:
        logging.error(f'Exception while setting webhook: {e}')


app = FastAPI(title='All-in-One-DeFi-Bot')


@app.on_event('startup')
async def _startup() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.info(f'✅ All-in-One-DeFi-Bot started | Service: {RAILWAY_SERVICE_NAME}')

    await send_telegram_message(f'✅ Bot started on service: **{RAILWAY_SERVICE_NAME}**')

    # ONLY the "bot" service sets the webhook
    if RAILWAY_SERVICE_NAME.lower() == "bot":
        full_webhook_url = f"{WEBHOOK_BASE_URL.rstrip('/')}/telegram/webhook"
        await delete_webhook()
        await asyncio.sleep(2)
        await set_webhook(full_webhook_url)
    else:
        logging.info(f'⏭️ Service {RAILWAY_SERVICE_NAME} - skipping webhook setup (not the bot service)')


@app.get('/')
@app.get('/health')
async def health() -> Dict[str, Any]:
    return {'ok': True, 'name': 'All-in-One-DeFi-Bot', 'service': RAILWAY_SERVICE_NAME}


@app.post('/telegram/webhook')
async def telegram_webhook(req: Request, background_tasks: BackgroundTasks) -> JSONResponse:
    try:
        payload = await req.json()
        logging.info(f"📥 Webhook received from Telegram | Service: {RAILWAY_SERVICE_NAME}")
    except:
        return JSONResponse({'ok': False}, status_code=400)

    message = (payload.get('message') or payload.get('edited_message')) or {}
    text = (message.get('text') or '').strip().lower()
    chat = message.get('chat') or {}
    chat_id = str(chat.get('id') or '')

    if text.startswith('/start'):
        await send_telegram_message('👋 Welcome! Type `/daily_pnl` for report.', chat_id)
        return JSONResponse({'ok': True})

    elif text in ('/daily_pnl', '/dailypnl'):
        background_tasks.add_task(process_daily_pnl, chat_id)
        return JSONResponse({'ok': True})

    else:
        await send_telegram_message('❓ Unknown command. Use /start or /daily_pnl', chat_id)

    return JSONResponse({'ok': True})


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=int(os.getenv('PORT', 8000)))