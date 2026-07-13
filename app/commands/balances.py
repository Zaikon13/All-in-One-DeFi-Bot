import os
import logging
from datetime import datetime, timezone


def _min_usd_display() -> float:
    """Holdings below this USD value are collapsed into one summary line.
    Env-configurable (WALLET_MIN_USD_DISPLAY, default $1). Defensive parse."""
    raw = os.getenv("WALLET_MIN_USD_DISPLAY", "1")
    try:
        v = float(raw)
        return v if v >= 0 else 1.0
    except (TypeError, ValueError):
        return 1.0


def _fmt_usd(v: float) -> str:
    return f"${v:,.2f}"


def _render_plain(wallet_address: str, balances: dict) -> str:
    """Pre-2026-07-05 amounts-only rendering — the exact fallback when pricing
    fails entirely (priced=False) or token_details is missing."""
    msg = f"**💰 Wallet Balances**\n\n"
    msg += f"🔑 `{wallet_address[:6]}...{wallet_address[-4:]}`\n\n"
    msg += f"🌟 **CRO**: `{balances.get('cro', 0):,.4f}`\n\n"
    msg += "**Tokens:**\n"
    tokens = balances.get('tokens', {})
    if tokens:
        for symbol, amount in sorted(tokens.items(), key=lambda x: x[1], reverse=True):
            if amount > 0.0001:
                msg += f"• **{symbol}**: `{amount:,.4f}`\n"
    else:
        msg += "No tokens found.\n"
    return msg


def _render_usd(wallet_address: str, balances: dict) -> str:
    """USD-enriched rendering (2026-07-05): total at top, holdings sorted by USD
    value desc, sub-threshold holdings collapsed, unpriced tokens shown with
    amount only and marked 'price unknown'."""
    min_usd = _min_usd_display()
    details = balances.get("token_details") or []
    cro = balances.get("cro", 0) or 0
    cro_usd = balances.get("cro_usd")
    usd_total = balances.get("usd_total")

    priced_rows = [d for d in details if d.get("usd") is not None]
    unpriced_rows = [d for d in details if d.get("usd") is None]
    priced_rows.sort(key=lambda d: d["usd"], reverse=True)
    unpriced_rows.sort(key=lambda d: d["amount"], reverse=True)

    big = [d for d in priced_rows if d["usd"] >= min_usd]
    small = [d for d in priced_rows if d["usd"] < min_usd]

    msg = f"**💰 Wallet Balances**\n\n"
    msg += f"🔑 `{wallet_address[:6]}...{wallet_address[-4:]}`\n\n"
    if usd_total is not None:
        note = " (excl. unpriced tokens)" if unpriced_rows else ""
        msg += f"**Total portfolio value: {_fmt_usd(usd_total)}**{note}\n\n"

    if cro_usd is not None:
        msg += f"🌟 **CRO**: `{cro:,.4f}` — {_fmt_usd(cro_usd)}\n\n"
    else:
        msg += f"🌟 **CRO**: `{cro:,.4f}` — price unknown\n\n"

    msg += "**Tokens:**\n"
    if not details:
        msg += "No tokens found.\n"
    else:
        for d in big:
            msg += f"• **{d['symbol']}**: `{d['amount']:,.4f}` — {_fmt_usd(d['usd'])}\n"
        MAX_UNPRICED_ROWS = 15  # Telegram 4096-char safety
        for d in unpriced_rows[:MAX_UNPRICED_ROWS]:
            msg += f"• **{d['symbol']}**: `{d['amount']:,.4f}` — price unknown\n"
        if len(unpriced_rows) > MAX_UNPRICED_ROWS:
            msg += f"• + {len(unpriced_rows) - MAX_UNPRICED_ROWS} more token(s), price unknown\n"
        if small:
            total_small = sum(d["usd"] for d in small)
            msg += f"• + {len(small)} more token(s) under {_fmt_usd(min_usd)} ({_fmt_usd(total_small)} combined)\n"
    return msg


async def get_all_balances(chat_id: str):
    """Modular /balances + /wallet command."""
    from app.main import WALLET_ADDRESS, send_telegram_message
    from core.wallet import get_wallet_balances

    if not WALLET_ADDRESS:
        await send_telegram_message("❌ WALLET_ADDRESS not set.", chat_id)
        return

    await send_telegram_message("📡 Fetching wallet balances...", chat_id)

    try:
        balances = await get_wallet_balances(WALLET_ADDRESS)

        # Honesty gate (2026-07-13): a failed/429/rejected fetch must NOT render as
        # "$0 / no tokens found". get_wallet_balances signals ok=False when the data
        # source is unavailable; say so plainly. Serves /wallet, /bal, /balances alike.
        if not balances.get("ok", True):
            await send_telegram_message(
                "⚠️ Couldn't fetch balances right now — data source unavailable.", chat_id)
            return

        # USD-enriched view when pricing worked; otherwise the exact legacy output.
        try:
            if balances.get("priced") and balances.get("token_details") is not None:
                msg = _render_usd(WALLET_ADDRESS, balances)
            else:
                msg = _render_plain(WALLET_ADDRESS, balances)
        except Exception as err:
            logging.error(f"USD render error (falling back to plain): {err}")
            msg = _render_plain(WALLET_ADDRESS, balances)

        msg += f"\n⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        await send_telegram_message(msg, chat_id)

    except Exception as e:
        logging.error(f"Balances error: {e}")
        await send_telegram_message("❌ Error fetching balances.", chat_id)
