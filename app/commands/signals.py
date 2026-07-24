"""/signals — live multi-chain discovery feed (2026-07-23). Same renderer
conventions as /wallet and /paper. Reads the discovery snapshot the worker
pushes onto the SAME state mirror as /paper (no second mechanism). Honest:
if nothing qualifies it says so, with the funnel numbers — never fabricates.
"""

import logging
from datetime import datetime, timezone

MIRROR_STALE_MINUTES = 30
_CHAIN_LABEL = {"cro": "cro", "solana": "solana", "sui-network": "sui"}


def _label(chain: str) -> str:
    return _CHAIN_LABEL.get(chain, chain)


def _fmt_usd(v) -> str:
    try:
        return f"${float(v):,.0f}"
    except (TypeError, ValueError):
        return "$?"


def render_signals(signals: dict | None, now_utc: datetime | None = None) -> str:
    """Pure renderer (unit-tested offline). `signals` is the worker's discovery
    snapshot: {chains, thresholds, funnel, recent, as_of}."""
    now_utc = now_utc or datetime.now(timezone.utc)
    if not signals or not isinstance(signals.get("chains"), list):
        return ("🔎 **Signals** — discovery feed is syncing from the worker "
                "(it pushes an update every scan cycle, ~5 min). Try again shortly.")

    chains = signals.get("chains") or []
    thresholds = signals.get("thresholds") or {}
    funnel = signals.get("funnel") or {}
    recent = signals.get("recent") or []

    msg = "🔎 **Live discovery feed** (multi-chain new pools)\n\n"

    # staleness
    try:
        as_of = datetime.fromisoformat(str(signals.get("as_of")))
        age_min = (now_utc - as_of).total_seconds() / 60.0
        if age_min > MIRROR_STALE_MINUTES:
            msg += f"⚠️ Data is {age_min:.0f} min old (worker may be restarting)\n\n"
    except Exception:
        pass

    # enabled chains + active thresholds
    thr_bits = []
    for c in chains:
        t = thresholds.get(c) or {}
        thr_bits.append(f"{_label(c)} (liq ≥ {_fmt_usd(t.get('min_liq'))}, score ≥ {t.get('min_score', '?')})")
    msg += "**Enabled:** " + " · ".join(thr_bits) + "\n\n"

    # most recent qualifying pools per chain
    for c in chains:
        rows = [r for r in recent if r.get("chain") == c]
        rows = sorted(rows, key=lambda r: r.get("ts") or "", reverse=True)[:5]
        msg += f"**{_label(c)}** — most recent qualifying:\n"
        if not rows:
            f = funnel.get(c) or {}
            msg += (f"- none this window (seen {f.get('seen', 0)}, matured "
                    f"{f.get('matured', 0)}, passed {f.get('passed', 0)})\n")
        else:
            for r in rows:
                msg += (f"- {r.get('tier', '')} **{r.get('symbol', '?')}/{r.get('quote', '?')}** "
                        f"score {r.get('score', 0):.0f} · {r.get('age_h', 0)}h · "
                        f"liq {_fmt_usd(r.get('liquidity'))} · vol1h {_fmt_usd(r.get('vol1h'))} · "
                        f"{r.get('buys', 0)}/{r.get('sells', 0)} b/s · {r.get('dex', '?')}\n")
        msg += "\n"

    # per-chain funnel line (this window)
    fn = []
    for c in chains:
        f = funnel.get(c) or {}
        seg = f"{_label(c)}: seen {f.get('seen', 0)}/matured {f.get('matured', 0)}/passed {f.get('passed', 0)}/sent {f.get('sent', 0)}"
        fn.append(seg)
    msg += "**Funnel (this window):** " + " · ".join(fn)
    return msg


async def get_signals(chat_id: str):
    """Bot-side /signals handler: render the worker's discovery mirror. Never
    raises to the webhook."""
    from app.main import send_telegram_message, get_signals_mirror
    try:
        await send_telegram_message(render_signals(get_signals_mirror()), chat_id)
    except Exception as e:
        logging.error(f"/signals error: {e}")
        await send_telegram_message("❌ Error building the signals report.", chat_id)
