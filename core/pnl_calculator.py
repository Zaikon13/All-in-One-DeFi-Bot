# Modular PnL Calculator for All-in-One-DeFi-Bot

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from core.dexscreener import get_token_price

class PnLCalculator:

    @staticmethod
    async def build_detailed_pnl_report(transactions: List[Dict], wallet: str) -> str:
        if not transactions:
            return "📭 No recent transactions found."

        # Group transactions by token symbol
        token_trades: Dict[str, List[Dict]] = {}
        for tx in transactions:
            try:
                symbol = tx.get('tokenSymbol', 'UNKNOWN')
                if symbol not in token_trades:
                    token_trades[symbol] = []
                token_trades[symbol].append(tx)
            except Exception:
                continue

        report = f"📊 **Daily Trade Report + Position PnL**\n\n"
        report += f"🔑 Wallet: `{wallet[:8]}...{wallet[-6:]}`\n"
        report += f"📆 Period: Last 24h activity\n\n"

        for symbol, trades in sorted(token_trades.items(), key=lambda x: len(x[1]), reverse=True)[:8]:
            try:
                # Calculate net position
                net_qty = 0.0
                trade_lines = []

                for tx in sorted(trades, key=lambda x: int(x.get('timeStamp', 0))):
                    decimals = int(tx.get('tokenDecimal', 18))
                    value = float(tx.get('value', 0)) / (10 ** decimals)
                    time_str = datetime.fromtimestamp(int(tx.get('timeStamp', 0))).strftime('%H:%M')

                    # Determine direction (very simplified - based on to/from if available)
                    to_addr = tx.get('to', '').lower()
                    from_addr = tx.get('from', '').lower()
                    wallet_lower = wallet.lower()

                    if to_addr == wallet_lower:
                        direction = "👉 BUY"
                        net_qty += value
                    else:
                        direction = "👋 SELL"
                        net_qty -= value

                    trade_lines.append(f"  {time_str} | {direction} {value:,.2f}")

                # Get current price
                # Note: We need contract address for accurate price. Using symbol as fallback.
                current_price = await get_token_price(trades[0].get('contractAddress', '')) if trades else None

                report += f"\n**{symbol}** ({len(trades)} trades)\n"
                report += "\n".join(trade_lines) + "\n"

                if net_qty != 0:
                    report += f"\n📊 **Net position**: {net_qty:+,.4f} {symbol}\n"

                    if current_price and current_price > 0:
                        position_value = abs(net_qty) * current_price
                        report += f"💰 **Current value**: ${position_value:,.2f} (at ${current_price:.6f})\n"

                        if net_qty > 0:
                            report += "📈 You are currently **long** this asset from today's activity.\n"
                        else:
                            report += "📉 You have **reduced** your position (sold more than bought).\n"
                    else:
                        report += "📈 Current price not available for exact PnL.\n"
                else:
                    report += "🔄 Position closed (bought and sold similar amounts).\n"

            except Exception as e:
                logging.warning(f"Error building report for {symbol}: {e}")
                continue

        report += "\n\n🔄 *Note: PnL is estimated from net position + current price. For precise cost-basis PnL we need historical prices.*"
        return report

    @staticmethod
    def build_pnl_report(transactions: List[Dict], wallet: str) -> str:
        # Keep old simple version for backward compatibility
        if not transactions:
            return "📭 No recent transactions found."

        report = f"📊 **Daily PnL Report**\n\n"
        report += f"🔑 Wallet: `{wallet[:8]}...{wallet[-6:]}`\n"
        report += f"📆 {len(transactions)} recent transactions\n\n"
        token_summary = {}
        for tx in transactions[:30]:
            try:
                symbol = tx.get('tokenSymbol', 'UNKNOWN')
                decimals = int(tx.get('tokenDecimal', 18))
                value = float(tx.get('value', 0)) / (10 ** decimals)
                time_str = datetime.fromtimestamp(int(tx.get('timeStamp', 0))).strftime('%d/%m %H:%M')
                report += f"• {time_str} | {symbol} | {value:+,.4f}\n"

                token_summary[symbol] = token_summary.get(symbol, 0) + value
            except:
                continue

        if token_summary:
            report += "\n**Quick Summary**\n"
            for symbol, total in sorted(token_summary.items(), key=lambda x: abs(x[1]), reverse=True)[:8]:
                report += f"• {symbol}: {total:+,.2f}\n"
        return report


# Backward compatibility
def build_pnl_report(transactions: List[Dict], wallet: str) -> str:
    return PnLCalculator.build_pnl_report(transactions, wallet)
