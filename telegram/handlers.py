# telegram/handlers.py - Telegram Command Handlers

import logging

from telegram import Update
from telegram.ext import ContextTypes

from core.pnl_calculator import get_daily_pnl_report


async def daily_pnl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /daily_pnl command (unified to production async Etherscan path)"""
    # Review Agent 2026-06-06: Unified Telegram command path to production async
    # get_daily_pnl_report() (Etherscan V2 via CronoScan). Legacy Covalent sync
    # no longer used here. Richer report (Top Movers + Grok insight) now delivered.
    # Error handling aligned with webhook path in app/main.py.
    await update.message.reply_text("🔄 Generating daily PnL report...")

    try:
        report = await get_daily_pnl_report()
        await update.message.reply_text(report, parse_mode="Markdown")
    except Exception as e:
        logging.exception("daily_pnl_command error")
        await update.message.reply_text("Error generating daily PnL report. Please try again.")


# Add more commands here as needed
# async def balances_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     pass
