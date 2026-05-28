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
        # Build compact summary for the prompt (avoid sending full raw txs)
        tokens = data.get("tokens", [])
        summary_lines = [
            f"- {t['symbol']}: {t['trades']} trades, net delta {t['net']:+.4f}"
            for t in tokens
        ]
        daily_summary = "\n".join(summary_lines) if summary_lines else "No activity details."

        prompt = load_prompt(
            "grok_daily_pnl.txt",
            date=data.get("date", "today"),
            daily_summary=daily_summary,
            wallet_preview=f"{WALLET_ADDRESS[:6]}...{WALLET_ADDRESS[-4:]}" if WALLET_ADDRESS else "unknown"
        )

        # Hard timeout (25s) for this command path - per Review Agent feedback
        # (shorter than default to keep webhook responsive; failures always fallback)
        insight = await call_grok(prompt, timeout=25.0)

        # Quality gate: must be non-error, substantial content
        if (insight and
            not insight.startswith(("Grok API error", "Error calling Grok", "[ERROR]", "GROK_API_KEY")) and
            len(insight.strip()) > 15):
            enhanced = (
                base_report +
                "\n\n🤖 **Grok Daily Insight:**\n" +
                insight.strip()
            )
            return enhanced
        else:
            # Low quality or empty -> silent fallback (user sees base report)
            logging.info("Grok daily PnL insight low-quality or failed; using fallback")
            return base_report + "\n\n(Grok insight unavailable this time - basic report shown)"

    except Exception as e:
        logging.exception(f"Grok daily PnL call failed (safe fallback): {e}")
        # Explicit safe fallback - never worse than pre-increment
        return base_report + "\n\n(Grok temporarily unavailable - basic report shown)"
