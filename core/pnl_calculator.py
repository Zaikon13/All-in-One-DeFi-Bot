# core/pnl_calculator.py - Accurate Daily PnL Calculator

import os
import traceback
from datetime import datetime
from typing import List, Dict

import httpx

COVALENT_API_KEY = os.getenv("COVALENT_API_KEY", "cqt_rQyD6PqwPyGkVvmWhBbyXWx9PxcD")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")

COVALENT_BASE = "https://api.covalenthq.com/v1"


def get_today_transactions() -> List[Dict]:
    """Fetch today's transactions using Covalent"""
    if not WALLET_ADDRESS:
        print("[ERROR] Missing WALLET_ADDRESS")
        return []

    today = datetime.now().strftime("%Y-%m-%d")
    url = f"{COVALENT_BASE}/25/address/{WALLET_ADDRESS}/transactions_v3/?key={COVALENT_API_KEY}"

    try:
        with httpx.Client(timeout=30) as client:
            r = client.get(url)
            print(f"[DEBUG] Covalent status: {r.status_code}")

            if r.status_code == 200:
                data = r.json()
                items = data.get("data", {}).get("items", [])
                print(f"[DEBUG] Total transactions: {len(items)}")

                today_tx = [tx for tx in items if tx.get("block_signed_at", "").startswith(today)]
                print(f"[DEBUG] Today's transactions: {len(today_tx)}")
                return today_tx
            else:
                print(f"[ERROR] Covalent API error: {r.text}")
    except Exception as e:
        print(f"[ERROR] Exception in get_today_transactions: {str(e)}")
        traceback.print_exc()
    return []


def calculate_daily_pnl() -> Dict:
    """Calculate accurate daily PnL per token"""
    try:
        transactions = get_today_transactions()
        if not transactions:
            return {"error": "No transactions today or API error. Check terminal logs for details."}

        token_data: Dict[str, Dict] = {}

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

    except Exception as e:
        print(f"[ERROR] Exception in calculate_daily_pnl: {str(e)}")
        traceback.print_exc()
        return {"error": f"Internal error: {str(e)}. Check terminal logs."}


def format_pnl_report(data: Dict) -> str:
    """Format clean Daily PnL report"""
    if "error" in data:
        return data["error"]

    lines = [
        f"📊 **Daily PnL Report** ({data['date']})",
        f"\n🔑 Wallet: {WALLET_ADDRESS[:6]}...{WALLET_ADDRESS[-4:]}",
        ""
    ]

    for token in data["tokens"]:
        lines.append(f"**{token['symbol']}** ({token['trades']} trades)")
        for trade in token["trades_list"]:
            lines.append(f"{trade['time']} | {trade['type']} {trade['amount']} {token['symbol']}")
        lines.append(f"**Net:** {token['net']:+.4f} {token['symbol']}")
        lines.append("")

    return "\n".join(lines)
