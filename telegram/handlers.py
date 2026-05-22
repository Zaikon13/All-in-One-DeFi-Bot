# telegram/handlers.py - Telegram Command Handlers

from telegram import Update
from telegram.ext import ContextTypes

from core.pnl_calculator import calculate_daily_pnl, format_pnl_report


async def daily_pnl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /daily_pnl command with accurate calculation"""
    await update.message.reply_text("🔄 Generating accurate Daily PnL report...")

    try:
        pnl_data = calculate_daily_pnl()
        report = format_pnl_report(pnl_data)
        await update.message.reply_text(report, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Error generating PnL report: {str(e)}")


# Add more commands here as needed
# async def balances_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     pass
