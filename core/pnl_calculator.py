# core/pnl_calculator.py - Simple & Working Daily PnL Calculator

import os
import logging
from datetime import datetime
from typing import List, Dict

import httpx

# Reuse Grok client (core/ preferred over duplication in app/main.py)
from core.grok_client import call_grok, load_prompt

COVALENT_API_KEY = os.getenv("COVALENT_API_KEY", "cqt_rQyD6PqwPyGkVvmWhBbyXWx9PxcD")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")

COVALENT_BASE = "https://api.covalenthq.com/v1"


def get_today_transactions() -> List[Dict]:
    """Fetch today's transactions (simple & reliable)"""
    if not WALLET_ADDRESS:
        print("[ERROR] Missing WALLET_ADDRESS")
        return []

    today = datetime.now().strftime("%Y-%m-%d")
    url = f"{COVALENT_BASE}/25/address/{WALLET_ADDRESS}/transactions_v3/?key={COVALENT_API_KEY}"

    try:
        with httpx.Client(timeout=30) as client:
            r = client.get(url)
            if r.status_code == 200:
                data = r.json()
                items = data.get("data", {}).get("items", [])
                today_tx = [tx for tx in items if tx.get("block_signed_at", "").startswith(today)]
                return today_tx
            else:
                print(f"[ERROR] Covalent status {r.status_code}")
    except Exception as e:
        print(f"[ERROR] {str(e)}")
    return []


def calculate_daily_pnl() -> Dict:
    """Calculate simple but correct daily PnL"""
    transactions = get_today_transactions()
    if not transactions:
        return {"error": "No transactions found today or API error."}

    token_data = {}

    for tx in transactions:
        for transfer in tx.get("transfers", []):
            symbol = transfer.get("contract_ticker_symbol", "CRO")
            decimals = transfer.get("contract_decimals", 18)
            amount = int(transfer.get("delta", 0)) / (10 ** decimals)
            tx_type = "BUY" if amount > 0 else "SELL"
            amount = abs(amount)

            if symbol not in token_data:
                token_data[symbol] = {"buys": 0, "sells": 0, "trades": []}

            if tx_type == "BUY":
                token_data[symbol]["buys"] += amount
            else:
                token_data[symbol]["sells"] += amount

            token_data[symbol]["trades"].append({
                "time": tx.get("block_signed_at", "")[11:16],
                "type": tx_type,
                "amount": round(amount, 4),
                "symbol": symbol
            })

    result = []
    for symbol, data in token_data.items():
        net = data["buys"] - data["sells"]
        result.append({
            "symbol": symbol,
            "trades": len(data["trades"]),
            "net": round(net, 4),
            "trades_list": data["trades"]
        })

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "tokens": result
    }


def format_pnl_report(data: Dict) -> str:
    """Format clean report"""
    if "error" in data:
        return data["error"]

    lines = [f"📊 **Daily PnL Report** ({data['date']})"]
    lines.append(f"\n🔑 Wallet: {WALLET_ADDRESS[:6]}...{WALLET_ADDRESS[-4:]}")
    lines.append("")

    for token in data["tokens"]:
        lines.append(f"**{token['symbol']}** ({token['trades']} trades)")
        for t in token["trades_list"]:
            lines.append(f"{t['time']} | {t['type']} {t['amount']} {token['symbol']}")
        lines.append(f"**Net:** {token['net']:+.4f} {token['symbol']}")
        lines.append("")

    return "\n".join(lines)


# -------------------------------------------------------------------
# Production async formatter for improved /daily_pnl quality (Option A, post-Review Agent 2026-05-28)
# Per refined brief: new function called EXCLUSIVELY from inside get_daily_pnl_report().
# Implements clean aggregates + Top Movers (Python-owned) + optional Grok insight (commentary only).
# -------------------------------------------------------------------
def format_daily_pnl_report(data: Dict, grok_insight: str | None = None) -> str:
    """Clean, modern daily PnL report for the production async path only.

    Production async formatter (used only by get_daily_pnl_report).
    Legacy sync path (telegram/handlers.py) continues to use the original format_pnl_report() unchanged.

    Post-Review Agent clarifications incorporated:
    - Grok Output Contract: Grok returns ONLY 3-6 sentence qualitative paragraph (no data/numbers/headers).
    - Telegram Markdown Safety: defensive comment on append; prompt enforces **bold** + simple lists only.
    - All structure/numbers computed here safely in Python.
    """
    if "error" in data:
        return data["error"]

    date = data.get("date", "today")
    tokens = data.get("tokens", [])
    wallet = WALLET_ADDRESS or "unknown"
    preview = f"{wallet[:6]}...{wallet[-4:]}" if len(wallet) > 10 else wallet

    total_trades = sum(t.get("trades", 0) for t in tokens)
    active_token_count = len(tokens)

    # Top movers by |net| (pre-computed for prompt + report; Python side only)
    sorted_tokens = sorted(tokens, key=lambda t: abs(t.get("net", 0)), reverse=True)
    top_movers = sorted_tokens[:5]

    lines = [
        f"📊 **Daily PnL — {date}**",
        "",
        f"🔑 Wallet: {preview}",
        f"Active tokens: {active_token_count} | Total trades: {total_trades}",
        "",
    ]

    if top_movers:
        lines.append("**Top Movers** (by |net delta|)")
        for t in top_movers:
            lines.append(f"• {t['symbol']} — net {t['net']:+.4f} ({t['trades']} trades)")
        lines.append("")

    if grok_insight:
        # Grok insight appended raw. Prompt strictly constrains output to safe Telegram Markdown v1.
        # If future changes relax the prompt, consider adding light escaping here.
        # (Review Agent clarification #2)
        lines.append("🤖 **Grok Daily Insight:**")
        lines.append(grok_insight.strip())
        lines.append("")

    return "\n".join(lines)


# -------------------------------------------------------------------
# Shared pure aggregation logic (reused by sync + async paths to avoid duplication)
# -------------------------------------------------------------------
def _aggregate_pnl(transactions: List[Dict]) -> Dict:
    """Pure function: aggregates Covalent tx list into daily net-delta PnL structure.
    Used by both calculate_daily_pnl (sync compat) and async path.
    """
    if not transactions:
        return {"error": "No transactions found today or API error."}

    token_data = {}

    for tx in transactions:
        for transfer in tx.get("transfers", []):
            symbol = transfer.get("contract_ticker_symbol", "CRO")
            decimals = transfer.get("contract_decimals", 18)
            amount = int(transfer.get("delta", 0)) / (10 ** decimals)
            tx_type = "BUY" if amount > 0 else "SELL"
            amount = abs(amount)

            if symbol not in token_data:
                token_data[symbol] = {"buys": 0, "sells": 0, "trades": []}

            if tx_type == "BUY":
                token_data[symbol]["buys"] += amount
            else:
                token_data[symbol]["sells"] += amount

            token_data[symbol]["trades"].append({
                "time": tx.get("block_signed_at", "")[11:16],
                "type": tx_type,
                "amount": round(amount, 4),
                "symbol": symbol
            })

    result = []
    for symbol, data in token_data.items():
        net = data["buys"] - data["sells"]
        result.append({
            "symbol": symbol,
            "trades": len(data["trades"]),
            "net": round(net, 4),
            "trades_list": data["trades"]
        })

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "tokens": result
    }


# -------------------------------------------------------------------
# Async-safe Covalent layer (addresses Review Agent High issue: async safety)
# Original sync get_today_transactions / calculate_daily_pnl kept UNCHANGED
# for compatibility with telegram/handlers.py (out of scope for this increment).
# -------------------------------------------------------------------

async def get_today_transactions_async() -> List[Dict]:
    """Async-safe fetch of today's transactions using Covalent (httpx.AsyncClient).
    Preferred for FastAPI/webhook/async contexts. Follows patterns from
    worker.py, core/wallet.py, core/dexscreener.py.
    """
    if not WALLET_ADDRESS:
        logging.error("[ERROR] Missing WALLET_ADDRESS")
        return []

    today = datetime.now().strftime("%Y-%m-%d")
    url = f"{COVALENT_BASE}/25/address/{WALLET_ADDRESS}/transactions_v3/?key={COVALENT_API_KEY}"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url)
            if r.status_code == 200:
                data = r.json()
                items = data.get("data", {}).get("items", [])
                today_tx = [tx for tx in items if tx.get("block_signed_at", "").startswith(today)]
                return today_tx
            else:
                logging.error(f"[ERROR] Covalent status {r.status_code}")
    except Exception as e:
        logging.error(f"[ERROR] Covalent async fetch: {str(e)}")
    return []


async def calculate_daily_pnl_async() -> Dict:
    """Async version of daily PnL calculation. Reuses _aggregate_pnl."""
    transactions = await get_today_transactions_async()
    return _aggregate_pnl(transactions)


# -------------------------------------------------------------------
# Public async entrypoint for production /daily_pnl (webhook path in app/main.py)
# -------------------------------------------------------------------
async def get_daily_pnl_report() -> str:
    """Generate daily PnL report with optional Grok AI enhancement + reliable fallback.

    Flow:
    - Fetch via async Covalent layer (preferred data source per GROK_COORDINATION).
    - If no meaningful txs: clean message.
    - Attempt Grok via core.grok_client.call_grok with HARD TIMEOUT (addresses prior High review feedback on timeout control).
    - Use compact prompt from prompts/grok_daily_pnl.txt + summarized data.
    - On success/good content: return base report + Grok insights.
    - On any failure (timeout, API error, low quality): clean fallback using format_pnl_report() style.
    - Never degrades UX below previous fallback quality.
    - Does not block event loop.

    LIMITATIONS (honest, per task scope and GROK_COORDINATION.md PnL priority):
    - This is NET DELTA ONLY (buys - sells per token for the day). NOT true realized USD PnL.
    - No cost basis, no entry/exit price tracking, no USD valuation of the deltas.
    - Covalent used here (consistency with Explorer used in balances/wallet paths is future refactor).
    - Full EOD scheduling / persistence / advanced cost basis out of scope for this small increment.
    """
    # Initial fetch (async safe)
    try:
        data = await calculate_daily_pnl_async()
    except Exception as e:
        logging.exception("daily_pnl_async fetch error")
        return "Error fetching daily transactions. Please try again later."

    # No data case (clean, no Grok needed)
    if "error" in data or not data.get("tokens"):
        return "📊 No meaningful transactions found today for PnL analysis."

    # Always produce the reliable base report (fallback quality floor)
    base_report = format_pnl_report(data)

    # Try Grok enhancement (with hard timeout for responsiveness/safety)
    try:
        # Build richer context for new prompt (post-Review Agent 2026-05-28, clarification #1):
        # total_trades, active_token_count, top_movers_summary (pre-computed in Python).
        # Old daily_summary removed (new prompt uses structured movers only; Grok forbidden from numbers).
        tokens = data.get("tokens", [])
        total_trades = sum(t.get("trades", 0) for t in tokens)
        active_token_count = len(tokens)
        sorted_movers = sorted(tokens, key=lambda t: abs(t.get("net", 0)), reverse=True)[:5]
        top_movers_lines = [
            f"- {m['symbol']}: net {m['net']:+.4f} ({m['trades']} trades)"
            for m in sorted_movers
        ]
        top_movers_summary = "\n".join(top_movers_lines) if top_movers_lines else "No activity."

        prompt = load_prompt(
            "grok_daily_pnl.txt",
            date=data.get("date", "today"),
            wallet_preview=f"{WALLET_ADDRESS[:6]}...{WALLET_ADDRESS[-4:]}" if WALLET_ADDRESS else "unknown",
            total_trades=total_trades,
            active_token_count=active_token_count,
            top_movers_summary=top_movers_summary
        )

        # Hard timeout (25s) for this command path - per Review Agent feedback
        # (shorter than default to keep webhook responsive; failures always fallback)
        insight = await call_grok(prompt, timeout=25.0)

        # Quality gate: must be non-error, substantial content
        if (insight and
            not insight.startswith(("Grok API error", "Error calling Grok", "[ERROR]", "GROK_API_KEY")) and
            len(insight.strip()) > 15):
            # Use the improved formatter for the production webhook path only.
            # Old format_pnl_report() remains untouched for telegram/handlers.py compatibility.
            # (Review Agent clarification #3 - legacy sync path protection; Option A)
            return format_daily_pnl_report(data, insight.strip())
        else:
            # Low quality or empty -> silent fallback (user sees base report)
            logging.info("Grok daily PnL insight low-quality or failed; using fallback")
            return base_report + "\n\n(Grok insight unavailable this time - basic report shown)"

    except Exception as e:
        logging.exception(f"Grok daily PnL call failed (safe fallback): {e}")
        # Explicit safe fallback - never worse than pre-increment
        return base_report + "\n\n(Grok temporarily unavailable - basic report shown)"
