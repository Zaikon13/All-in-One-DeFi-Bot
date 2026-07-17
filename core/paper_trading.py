"""Paper-trading engine — SIMULATION ONLY (2026-07-17).

There are no real transactions, no private keys, and no spending capability
anywhere in this module or this codebase. It simulates entries/exits against
live prices to produce EVIDENCE about the scanner's judgment. Real-fund
execution does not exist here and only becomes discussable after simulation
produces evidence AND risk controls exist (see CLAUDE.md roadmap gate).

Design:
- State (simulated balance, open positions, closed trades) lives in
  paper_state.json under the worker's persistence dir (/data on Railway), so it
  survives redeploys. Atomic writes, defensive loads.
- Decision logic is pure functions (should_enter / check_exit / close math) —
  unit-tested offline with no network.
- The worker owns the engine (it has the volume + the scanner). A /paper command
  served from a worker-pushed mirror is planned for the NEXT commit.
"""

import json
import logging
import math
import os
from datetime import datetime, timezone

# --- env knobs (defensive parse; all simulation-only) ---------------------------


def _env_pos_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        v = float(raw)
        if not math.isfinite(v) or v <= 0:
            raise ValueError
        return v
    except (TypeError, ValueError):
        logging.warning(f"[paper] invalid {name}={raw!r}; using default {default}")
        return default


PAPER_TRADING_ENABLED = os.getenv("PAPER_TRADING_ENABLED", "true").lower() == "true"
PAPER_STARTING_USD = _env_pos_float("PAPER_STARTING_USD", 1000.0)
PAPER_ENTRY_SCORE = _env_pos_float("PAPER_ENTRY_SCORE", 70.0)
PAPER_POSITION_USD = _env_pos_float("PAPER_POSITION_USD", 50.0)
PAPER_MAX_OPEN = int(_env_pos_float("PAPER_MAX_OPEN", 5.0))
PAPER_TP_PCT = _env_pos_float("PAPER_TP_PCT", 25.0)
PAPER_SL_PCT = _env_pos_float("PAPER_SL_PCT", 15.0)
PAPER_MAX_HOLD_HOURS = _env_pos_float("PAPER_MAX_HOLD_HOURS", 24.0)


def data_dir() -> str:
    """Same resolution as the worker's persistence base (kept in sync with
    worker.PERSISTENCE_BASE): WORKER_DATA_DIR -> RAILWAY_VOLUME_MOUNT_PATH -> ./data."""
    return (os.getenv("WORKER_DATA_DIR")
            or os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
            or "data")


def state_path() -> str:
    return os.path.join(data_dir(), "paper_state.json")


# --- state I/O (never raises) ----------------------------------------------------


def fresh_state() -> dict:
    return {"balance_usd": PAPER_STARTING_USD, "starting_usd": PAPER_STARTING_USD,
            "open": [], "closed": []}


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _valid_open(p) -> bool:
    """An open position the engine can actually manage (price, exit, close)."""
    return (isinstance(p, dict)
            and _is_num(p.get("entry_price")) and p["entry_price"] > 0
            and _is_num(p.get("qty")) and p["qty"] > 0
            and _is_num(p.get("usd_in")) and p["usd_in"] > 0
            and bool(p.get("pair_address")) and bool(p.get("token_address")))


def load_state(path: str | None = None) -> dict:
    """Load paper state; missing/corrupt/partial files degrade to a valid state.
    Element-level sanitation (2026-07-17 review M1): malformed open/closed entries
    are dropped with a log (a hand-edited zombie position must not wedge the
    engine or hold a slot forever); numeric fields accept int or float."""
    p = path or state_path()
    try:
        with open(p, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return fresh_state()
        st = fresh_state()
        for k in ("balance_usd", "starting_usd"):
            if _is_num(raw.get(k)):
                st[k] = float(raw[k])
        if isinstance(raw.get("closed"), list):
            st["closed"] = [c for c in raw["closed"] if isinstance(c, dict)]
        if isinstance(raw.get("open"), list):
            good = [q for q in raw["open"] if _valid_open(q)]
            dropped = len(raw["open"]) - len(good)
            if dropped:
                logging.warning(f"[paper] dropped {dropped} malformed open position(s) on load")
            st["open"] = good
        return st
    except FileNotFoundError:
        return fresh_state()
    except Exception as e:
        logging.error(f"[paper] state load failed ({e}); starting fresh (old file kept)")
        return fresh_state()


def save_state(state: dict, path: str | None = None) -> bool:
    """Atomic tmp+replace write; never raises. Returns success."""
    p = path or state_path()
    try:
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, p)
        return True
    except Exception as e:
        logging.error(f"[paper] state save failed: {e}")
        return False


# --- pure decision logic (unit-tested offline) -----------------------------------


def should_enter(score, price, open_count, balance_usd, already_open,
                 entry_score=None, position_usd=None, max_open=None):
    """(ok, reason). Entry only on a finite score >= entry bar, a usable price,
    a free slot, sufficient simulated balance, and no existing position on the
    same pair."""
    entry_score = PAPER_ENTRY_SCORE if entry_score is None else entry_score
    position_usd = PAPER_POSITION_USD if position_usd is None else position_usd
    max_open = PAPER_MAX_OPEN if max_open is None else max_open
    try:
        score = float(score)
        price = float(price)
    except (TypeError, ValueError):
        return False, "bad data"
    if not (math.isfinite(score) and math.isfinite(price)) or price <= 0:
        return False, "bad data"
    if score < entry_score:
        return False, f"score {score:.0f} below entry bar {entry_score:.0f}"
    if already_open:
        return False, "already holding this pair"
    if open_count >= max_open:
        return False, f"max open positions ({max_open}) reached"
    if balance_usd < position_usd:
        return False, f"insufficient simulated balance (${balance_usd:.2f})"
    return True, "ok"


def open_position(state: dict, pair_address: str, symbol: str, token_address: str,
                  price: float, score: float, now_iso: str,
                  position_usd: float | None = None) -> dict:
    """Mutates state: deduct position size, append the open position. Returns it."""
    usd = PAPER_POSITION_USD if position_usd is None else position_usd
    pos = {
        "pair_address": (pair_address or "").lower(),
        "symbol": symbol or "?",
        "token_address": (token_address or "").lower(),
        "entry_price": float(price),
        "qty": usd / float(price),
        "usd_in": usd,
        "score": round(float(score), 1),
        "opened_at": now_iso,
    }
    state["balance_usd"] -= usd
    state["open"].append(pos)
    return pos


def check_exit(position: dict, current_price, now_utc,
               tp_pct=None, sl_pct=None, max_hold_hours=None):
    """None (hold) or (reason, exit_price). First rule hit wins: TP, then SL,
    then time-stop. Missing/bad price NEVER exits — hold and retry next cycle."""
    tp_pct = PAPER_TP_PCT if tp_pct is None else tp_pct
    sl_pct = PAPER_SL_PCT if sl_pct is None else sl_pct
    max_hold_hours = PAPER_MAX_HOLD_HOURS if max_hold_hours is None else max_hold_hours
    entry = position.get("entry_price") or 0
    price = None
    try:
        if current_price is not None:
            p = float(current_price)
            if math.isfinite(p) and p > 0:
                price = p
    except (TypeError, ValueError):
        price = None
    if price is not None and entry > 0:
        move_pct = (price - entry) / entry * 100.0
        if move_pct >= tp_pct:
            return "take-profit", price
        if move_pct <= -sl_pct:
            return "stop-loss", price
    # time-stop uses last known price if current is missing? NO — a time-stop with
    # no price cannot be booked honestly; wait for a price (spec: never exit on
    # missing data). With a price, time-stop closes at that price.
    if price is not None:
        try:
            opened = datetime.fromisoformat(str(position.get("opened_at")))
            if opened.tzinfo is None:
                opened = opened.replace(tzinfo=timezone.utc)
            held_h = (now_utc - opened).total_seconds() / 3600.0
            if held_h >= max_hold_hours:
                return "time-stop", price
        except Exception:
            pass  # bad timestamp -> no time exit; TP/SL still work
    return None


def close_position(state: dict, position: dict, exit_price: float, reason: str,
                   now_iso: str) -> dict:
    """Mutates state: credit proceeds, move position to closed with realized PnL."""
    proceeds = position["qty"] * float(exit_price)
    pnl = proceeds - position["usd_in"]
    closed = dict(position)
    closed.update({
        "exit_price": float(exit_price),
        "exit_reason": reason,
        "closed_at": now_iso,
        "pnl_usd": round(pnl, 2),
        "pnl_pct": round((float(exit_price) - position["entry_price"])
                         / position["entry_price"] * 100.0, 2) if position["entry_price"] else 0.0,
    })
    state["balance_usd"] += proceeds
    state["open"] = [p for p in state["open"]
                     if p.get("pair_address") != position.get("pair_address")]
    state["closed"].append(closed)
    return closed


def win_rate(state: dict):
    closed = state.get("closed") or []
    if not closed:
        return None
    wins = sum(1 for c in closed if (c.get("pnl_usd") or 0) > 0)
    return 100.0 * wins / len(closed)


def total_equity_pnl(state: dict) -> float:
    """Realized PnL since start: (balance + open cost basis) - starting capital.
    (Open positions are carried at cost here — unrealized PnL needs live prices
    and is shown only where prices are available, e.g. /paper.)"""
    invested = sum(p.get("usd_in", 0) for p in state.get("open") or [])
    return (state.get("balance_usd", 0) + invested) - state.get("starting_usd", 0)


def paper_summary_line(state: dict) -> str:
    """One-line status (EOD wiring lands in the /paper commit). Markdown v1 safe."""
    wr = win_rate(state)
    wr_s = "—" if wr is None else f"{wr:.0f}%"
    return (f"🧪 Paper: balance ${state.get('balance_usd', 0):,.2f} · "
            f"open {len(state.get('open') or [])} · "
            f"closed {len(state.get('closed') or [])} · win rate {wr_s}")


def sanitize_symbol(sym: str) -> str:
    """Strip Telegram Markdown v1 entity chars (same rationale as the digest)."""
    import re
    return re.sub(r"[*_\[\]`]", "", str(sym or "")).strip() or "?"
