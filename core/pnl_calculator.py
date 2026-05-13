# Modular PnL Calculator - Hotfix version with better error handling

import logging
from datetime import datetime
from typing import List, Dict
from core.dexscreener import get_token_price

class PnLCalculator:

    @staticmethod
    async def build_advanced_pnl_report(transactions: List[Dict], wallet: str) -> str:
        if not transactions:
            return "📭 No recent transactions found."

        report = "📊 **Advanced Daily PnL Report (USDT)**\n\n"
        report += f"🔑 Wallet: `{wallet[:8]}...{wallet[-6:]}`\n\n"

        # Simple grouping by token
        from collections import defaultdict
        token_groups = defaultdict(list)
        for tx in transactions:
            symbol = tx.get('tokenSymbol', 'UNKNOWN')
            token_groups[symbol].append(tx)

        for symbol, trades in list(token_groups.items())[:8]:  # limit to 8 tokens
            try:
                contract = trades[0].get('contractAddress', '')
                price = await get_token_price(contract) if contract else None

                net = 0.0
                lines = []
                for tx in trades:
                    decimals = int(tx.get('tokenDecimal', 18))
                    amount = int(tx.get('value', 0)) / (10 ** decimals)
                    ts = int(tx.get('timeStamp', 0))
                    time_str = datetime.fromtimestamp(ts).strftime('%H:%M')
                    direction = 'BUY' if tx.get('to','').lower() == wallet.lower() else 'SELL'
                    net += amount if direction == 'BUY' else -amount
                    usdt = f' ~${amount*price:,.2f}' if price else ''
                    lines.append(f"  {time_str} | {direction} {amount:,.0f}{usdt}")

                report += f"**{symbol}** ({len(trades)} trades)\n"
                report += '\n'.join(lines[:6]) + '\n'  # limit lines
                if net > 0:
                    report += f"Net: +{net:,.0f} {symbol}"
                    if price:
                        report += f" | Value ~${net*price:,.2f} USDT"
                report += '\n\n'
            except Exception as e:
                logging.error(f"Error in {symbol}: {e}")
                report += f"**{symbol}** - error processing\n\n"
                continue

        report += "\n_If no output, try again in a moment._"
        return report

    @staticmethod
    def build_pnl_report(transactions: List[Dict], wallet: str) -> str:
        return "Using advanced report..."

# Fallback
def build_pnl_report(transactions: List[Dict], wallet: str) -> str:
    return PnLCalculator.build_pnl_report(transactions, wallet)
