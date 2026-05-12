import httpx
import logging
from datetime import datetime

async def get_all_balances(chat_id: str):
    """Modular /balances command"""
    from app.main import WALLET_ADDRESS, send_telegram_message
    from core.wallet import get_wallet_balances
    
    if not WALLET_ADDRESS:
        await send_telegram_message("❌ WALLET_ADDRESS not set.", chat_id)
        return

    await send_telegram_message("📡 Fetching wallet balances...", chat_id)

    try:
        balances = await get_wallet_balances(WALLET_ADDRESS)
        
        msg = f"**💰 Wallet Balances**\n\n"
        msg += f"🔑 `{WALLET_ADDRESS[:6]}...{WALLET_ADDRESS[-4:]}`\n\n"
        msg += f"🌟 **CRO**: `{balances.get('cro', 0):,.4f}`\n\n"
        msg += "**Tokens:**\n"

        tokens = balances.get('tokens', {})
        if tokens:
            for symbol, amount in sorted(tokens.items(), key=lambda x: x[1], reverse=True):
                if amount > 0.0001:
                    msg += f"• **{symbol}**: `{amount:,.4f}`\n"
        else:
            msg += "No tokens found.\n"

        msg += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
        await send_telegram_message(msg, chat_id)

    except Exception as e:
        logging.error(f"Balances error: {e}")
        await send_telegram_message("❌ Error fetching balances.", chat_id)
