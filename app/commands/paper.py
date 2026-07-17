"""/paper — simulated portfolio status (2026-07-17). SIMULATION ONLY.

Renders from the in-memory mirror the worker pushes to /internal/paper-state
(the /data volume attaches only to the worker, so the bot cannot read
paper_state.json directly). Same renderer conventions as /wallet: Markdown v1,
phone-friendly, honest about missing data.
"""

import logging
from datetime import datetime, timezone

from core.paper_trading import total_equity_pnl, win_rate

MIRROR_STALE_MINUTES = 30


def _fmt_price(p: float) -> str:
    if p >= 1:
        return f"${p:,.4f}"
    if p >= 0.01:
        return f"${p:.4f}"
    return f"${p:.8f}"


def render_paper_status(mirror: dict | None, prices: dict | None = None,
                        now_utc: datetime | None = None) -> str:
    """Pure renderer (unit-tested offline). mirror = {"state": ..., "as_of": iso}.
    prices maps token_address -> current USD price (may be empty/None)."""
    now_utc = now_utc or datetime.now(timezone.utc)
    if not mirror or not isinstance(mirror.get("state"), dict):
        return ("🧪 **Paper trading**\n\n"
                "State is syncing from the worker (it pushes an update every scan "
                "cycle, ~5 min). Try again shortly.")
    st = mirror["state"]
    prices = prices or {}

    msg = "🧪 **Paper trading** (simulation only — no real funds)\n\n"

    # staleness note
    try:
        as_of = datetime.fromisoformat(str(mirror.get("as_of")))
        age_min = (now_utc - as_of).total_seconds() / 60.0
        if age_min > MIRROR_STALE_MINUTES:
            msg += f"⚠️ Data is {age_min:.0f} min old (worker may be restarting)\n\n"
    except Exception:
        pass

    realized = total_equity_pnl(st)
    msg += (f"**Balance:** ${st.get('balance_usd', 0):,.2f} "
            f"(started ${st.get('starting_usd', 0):,.0f}, "
            f"realized {realized:+,.2f})\n\n")

    opens = st.get("open") or []
    msg += f"**Open positions ({len(opens)}):**\n"
    if not opens:
        msg += "- none — waiting for a 🔥-tier pair (patience IS the strategy)\n"
    for p in opens:
        cp = prices.get(p.get("token_address"))
        line = f"- **{p.get('symbol','?')}**: in {_fmt_price(p.get('entry_price', 0))}"
        if cp:
            unreal = p.get("qty", 0) * cp - p.get("usd_in", 0)
            pct = (cp - p["entry_price"]) / p["entry_price"] * 100.0 if p.get("entry_price") else 0.0
            line += f" · now {_fmt_price(cp)} · unrealized {unreal:+,.2f} USD ({pct:+.1f}%)"
        else:
            line += " · current price unknown this minute"
        msg += line + "\n"

    closed = st.get("closed") or []
    msg += f"\n**Closed trades ({len(closed)} total, last {min(10, len(closed))}):**\n"
    if not closed:
        msg += "- none yet\n"
    for c in closed[-10:][::-1]:
        emoji = "✅" if (c.get("pnl_usd") or 0) > 0 else "❌"
        msg += (f"- {emoji} **{c.get('symbol','?')}** {c.get('pnl_usd', 0):+,.2f} USD "
                f"({c.get('pnl_pct', 0):+.1f}%) · {c.get('exit_reason','?')}\n")

    wr = win_rate(st)
    msg += f"\n**Win rate:** {'—' if wr is None else f'{wr:.0f}%'}"
    return msg


async def get_paper_status(chat_id: str):
    """Bot-side /paper handler: mirror + one Dexscreener batch for open-position
    prices (keyless GET; zero Explorer calls). Never raises to the webhook."""
    from app.main import send_telegram_message, get_paper_mirror

    try:
        mirror = get_paper_mirror()
        prices = {}
        opens = ((mirror or {}).get("state") or {}).get("open") or []
        addrs = [p.get("token_address") for p in opens if p.get("token_address")]
        if addrs:
            try:
                import httpx
                from core.wallet import get_token_prices
                async with httpx.AsyncClient(timeout=15.0) as client:
                    prices = await get_token_prices(client, addrs)
            except Exception as e:
                logging.info(f"/paper price fetch failed (showing entries only): {e}")
        await send_telegram_message(render_paper_status(mirror, prices), chat_id)
    except Exception as e:
        logging.error(f"/paper error: {e}")
        await send_telegram_message("❌ Error building the paper report.", chat_id)
