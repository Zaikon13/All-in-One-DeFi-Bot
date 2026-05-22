# core/pnl_calculator.py - Accurate Daily PnL Calculator

import os
from datetime import datetime, timedelta
from typing import List, Dict

import httpx

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")


def get_today_transactions() -> List[Dict]:
    """Fetch only today's transactions from Cronos via Etherscan"""
    if not (ETHERSCAN_API_KEY and WALLET_ADDRESS):
        print("Missing ETHERSCAN_API_KEY or WALLET_ADDRESS")
        return []

    today = datetime.now().date()
    start_time = int(datetime.combine(today, datetime.min.time()).timestamp())
    end_time = int(datetime.combine(today, datetime.max.time()).timestamp())

    # Correct Etherscan V2 API for Cronos
    url = (
        f"https://api.etherscan.io/v2/api?chainid=25"
        f"&module=account&action=txlist"
        f"&address={WALLET_ADDRESS}"
        f"&startblock=0&endblock=99999999"
        f"&sort=asc&apikey={ETHERSCAN_API_KEY}"
    )

    try:
        with httpx.Client(timeout=30) as client:
            r = client.get(url)
            print(f"Etherscan status: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                print(f"Etherscan response status: {data.get('status')}")
                if data.get("status") == "1":
                    all_tx = data.get("result", [])
                    today_tx = [
                        tx for tx in all_tx
                        if start_time <= int(tx.get("timeStamp", 0)) <= end_time
                    ]
                    print(f"Found {len(today_tx)} transactions today")
                    return today_tx
                else:
                    print(f"Etherscan error: {data.get('message')}")
    except Exception as e:
        print(f"Etherscan exception: {e}")
    return []


def calculate_daily_pnl() -> Dict:
    """Calculate accurate daily PnL per token"""
    transactions = get_today_transactions()
    if not transactions:
        return {"error": "No transactions today or API error. Check logs."}

    token_data: Dict[str, Dict] = {}

    for tx in transactions:
        token_symbol = tx.get("tokenSymbol", "CRO")
        token_decimal = int(tx.get("tokenDecimal", 18))
        value = int(tx.get("value", 0)) / (10 ** token_decimal)
        tx_type = "BUY" if tx.get("to", "").lower() == WALLET_ADDRESS.lower() else "SELL"

        if token_symbol not in token_data:
            token_data[token_symbol] = {
                "buys": 0,
                "sells": 0,
                "trades": []
            }

        if tx_type == "BUY":
            token_data[token_symbol]["buys"] += value
        else:
            token_data[token_symbol]["sells"] += value

        token_data[token_symbol]["trades"].append({
            "time": datetime.fromtimestamp(int(tx.get("timeStamp", 0))).strftime("%H:%M"),
            "type": tx_type,
            "amount": round(value, 4),
            "symbol": token_symbol
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
    """Format beautiful Daily PnL report"""
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
