# Modular PnL Calculator for All-in-One-DeFi-Bot (Advanced version with USDT values)

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from core.dexscreener import get_token_price

class PnLCalculator:

    @staticmethod
    async def build_advanced_pnl_report(transactions: List[Dict], wallet: str) -> str:
        """
        Advanced per-asset daily report with USDT values.
        Groups trades by token, shows sequence of buys/sells,
        net position, and current value in USDT.
        """
        if not transactions:
            return "📭 No recent transactions found."

        # Group by token symbol
        token_trades: Dict[str, List[Dict]] = {}
        for tx in transactions:
            try:
                symbol = tx.get('tokenSymbol', 'UNKNOWN')
                if symbol not in token_trades:
                    token_trades[symbol] = []
                token_trades[symbol].append(tx)
            except:
                continue

        report = "📊 **Advanced Daily Trade Report + Position PnL (USDT)**\n\n"
        report += f"🔑 Wallet: `{wallet[:8]}...{wallet[-6:]}`\n"
        report += "📆 Showing last 24h activity with live USDT values\n\n"

        processed = 0
        for symbol, trades in sorted(token_trades.items(), key=lambda x: len(x[1]), reverse=True):
            if processed >= 6:  # Limit to top 6 most active tokens
                break
            processed += 1

            try:
                # Get current price (best effort)
                contract_address = trades[0].get('contractAddress', '') if trades else ''
                current_price = await get_token_price(contract_address) if contract_address else None

                # Calculate net position + build trade list
                net_qty = 0.0
                total_bought = 0.0
                total_sold = 0.0
                trade_lines = []

                for tx in sorted(trades, key=lambda x: int(x.get('timeStamp', 0))):
                    decimals = int(tx.get('tokenDecimal', 18))
                    raw_value = float(tx.get('value', 0))
                    amount = raw_value / (10 ** decimals)
                    time_str = datetime.fromtimestamp(int(tx.get('timeStamp', 0))).strftime('%H:%M')

                    to_addr = tx.get('to', '').lower()
                    wallet_lower = wallet.lower()

                    if to_addr == wallet_lower:
                        direction = "👉 BUY"
                        net_qty += amount
                        total_bought += amount
                    else:
                        direction = "👋 SELL"
                        net_qty -= amount
                        total_sold += amount

                    # USDT value of this specific trade (using current price as approximation)
                    usdt_value = amount * current_price if current_price else 0
                    usdt_str = f" (~${usdt_value:,.2f})" if current_price else ""

                    trade_lines.append(f"  {time_str} | {direction} {amount:,.2f}{usdt_str}")

                # Build the report section for this token
                report += f"\n**{symbol}** ({len(trades)} trades)\n"
                report += "\n".join(trade_lines) + "\n"

                # Summary for this token
                if net_qty > 0.0001:
                    report += f"\n📊 **Net Position**: +{net_qty:,.4f} {symbol} (long from today's activity)\n"
                    if current_price:
                        position_value = net_qty * current_price
                        report += f"💰 **Current Value**: ${position_value:,.2f} USDT @ ${current_price:.6f}\n"
                        report += "📈 You are currently **holding** this position.\n"
                elif net_qty < -0.0001:
                    report += f"\n📊 **Net Position**: {net_qty:,.4f} {symbol} (you sold more than you bought today)\n"
                    if current_price:
                        report += f"📉 You have **reduced exposure** to this asset.\n"
                else:
                    report += "🔄 Position roughly closed (bought ≈ sold).\n"

                # Extra insight
                if total_bought > 0 and total_sold > 0:
                    report += f"🔄 You bought {total_bought:,.2f} and sold {total_sold:,.2f} today.\n"

            except Exception as e:
                logging.warning(f"Error processing {symbol}: {e}")
                continue

        if processed == 0:
            report += "No meaningful token activity found in the last 24h.\n"

        report += "\n\n🔄 *USDT values are calculated using current live price (approximation). For exact historical cost-basis PnL we would need price at time of each trade.*"
        return report

    @staticmethod
    def build_pnl_report(transactions: List[Dict], wallet: str) -> str:
        # Simple fallback version
        if not transactions:
            return "📭 No recent transactions found."

        report = f"📊 **Daily PnL Report**\n\n"
        report += f"🔑 Wallet: `{wallet[:8]}...{wallet[-6:]}`\n"
        report += f"📆 {len(transactions)} recent transactions\n\n"

        token_summary = {}
        for tx in transactions[:25]:
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
