# Modular PnL Calculator for All-in-One-DeFi-Bot

import logging
from datetime import datetime
from typing import List, Dict, Any

class PnLCalculator:
    @staticmethod
    def build_pnl_report(transactions: List[Dict], wallet: str) -> str:
        if not transactions:
            return "📭 No recent transactions found."

        report = f"📊 **Daily PnL Report**\n\n"
        report += f"🔑 Wallet: `{wallet[:8]}...{wallet[-6:]}`\n"
        report += f"📦 {len(transactions)} recent transactions\n\n"

        # Group by token for summary
        token_summary = {}
        for tx in transactions[:50]:  # Limit for performance
            try:
                symbol = tx.get('tokenSymbol', 'UNKNOWN')
                decimals = int(tx.get('tokenDecimal', 18))
                value_raw = float(tx.get('value', 0))
                value = value_raw / (10 ** decimals)
                time_str = datetime.fromtimestamp(int(tx.get('timeStamp', 0))).strftime('%d/%m %H:%M')

                report += f"• {time_str} | {symbol} | {value:+,.4f}\n"

                if symbol in token_summary:
                    token_summary[symbol] += value
                else:
                    token_summary[symbol] = value
            except Exception as e:
                logging.warning(f"Error processing tx: {e}")
                continue

        # Add summary
        if token_summary:
            report += "\n**Token Summary**\n"
            for symbol, total in sorted(token_summary.items(), key=lambda x: abs(x[1]), reverse=True)[:10]:
                report += f"• {symbol}: {total:+,.2f}\n"

        return report

# For backward compatibility
def build_pnl_report(transactions: List[Dict], wallet: str) -> str:
    return PnLCalculator.build_pnl_report(transactions, wallet)
