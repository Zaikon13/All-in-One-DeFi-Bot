# worker.py - All-in-One-DeFi-Bot Worker Loop (Improved)

import asyncio
import logging
from datetime import datetime
import os

import httpx
from core.dexscreener import get_new_cronos_pairs
from core.wallet import get_wallet_balances

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")

HEARTBEAT_INTERVAL = 3600
DEXSCREENER_INTERVAL = 300
WALLET_CHECK_INTERVAL = 600  # 10 minutes

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("worker")


class WorkerLoop:
    def __init__(self):
        self.running = True
        self.known_pairs: set[str] = set()
        self.last_wallet_state: dict | None = None

    async def send_telegram(self, text: str):
        if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
            logger.warning("Telegram credentials not configured - skipping send")
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                await client.post(
                    url,
                    json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
                )
        except Exception as e:
            logger.error(f"Telegram send error: {e}")

    async def heartbeat(self):
        while self.running:
            ts = datetime.now().strftime("%H:%M")
            msg = f"💓 **Worker Heartbeat**\n\n**Time:** {ts}\n**Status:** Online\n**Next:** in 1 hour"
            await self.send_telegram(msg)
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def poll_dexscreener(self):
        """Real new pair detection with alerts."""
        while self.running:
            try:
                new_pairs = await get_new_cronos_pairs(self.known_pairs, limit=3)

                for pair in new_pairs:
                    liq = pair.get("liquidityUsd") or 0
                    fdv = pair.get("fdv") or 0
                    vol = pair.get("volume24h") or 0

                    msg = (
                        f"🚀 **New Pair Detected on Cronos**\n\n"
                        f"**{pair['baseSymbol']} / {pair['quoteSymbol']}**\n"
                        f"**Price:** ${pair.get('priceUsd', 'N/A')}\n"
                        f"**Liquidity:** ${liq:,.0f}\n"
                        f"**FDV:** ${fdv:,.0f}\n"
                        f"**24h Volume:** ${vol:,.0f}\n\n"
                        f"[View on DexScreener]({pair['url']})"
                    )
                    await self.send_telegram(msg)
                    logger.info(f"New pair alert sent: {pair['baseSymbol']}/{pair['quoteSymbol']}")

                if new_pairs:
                    logger.info(f"Found {len(new_pairs)} new pair(s) on Cronos")

            except Exception as e:
                logger.error(f"DexScreener polling error: {e}")

            await asyncio.sleep(DEXSCREENER_INTERVAL)

    async def monitor_wallet(self):
        """Periodic wallet balance monitoring with change alerts."""
        if not WALLET_ADDRESS:
            logger.warning("WALLET_ADDRESS not set - wallet monitoring disabled")
            await asyncio.sleep(WALLET_CHECK_INTERVAL)
            return

        while self.running:
            try:
                balances = await get_wallet_balances(WALLET_ADDRESS)
                current_state = {
                    "cro": round(balances["cro"], 4),
                    "tokens": {k: round(v, 6) for k, v in balances["tokens"].items() if v > 0.0001}
                }

                if self.last_wallet_state is not None:
                    # Detect significant CRO change
                    old_cro = self.last_wallet_state.get("cro", 0)
                    new_cro = current_state["cro"]
                    if abs(new_cro - old_cro) > 0.5:  # > 0.5 CRO change
                        diff = new_cro - old_cro
                        await self.send_telegram(
                            f"💰 **CRO Balance Change**\n\n"
                            f"**New:** {new_cro:,.4f} CRO\n"
                            f"**Change:** {diff:+.4f} CRO\n"
                            f"**Wallet:** `{WALLET_ADDRESS[:6]}...{WALLET_ADDRESS[-4:]}`"
                        )

                    # Simple token change detection (top tokens)
                    old_tokens = self.last_wallet_state.get("tokens", {})
                    for symbol, amount in current_state["tokens"].items():
                        old_amount = old_tokens.get(symbol, 0)
                        if abs(amount - old_amount) > 1 and amount > 0.1:
                            diff = amount - old_amount
                            await self.send_telegram(
                                f"🪙 **{symbol} Balance Change**\n\n"
                                f"**New:** {amount:,.4f} {symbol}\n"
                                f"**Change:** {diff:+.4f} {symbol}"
                            )

                self.last_wallet_state = current_state
                logger.info(f"Wallet check complete - CRO: {current_state['cro']}")

            except Exception as e:
                logger.error(f"Wallet monitoring error: {e}")

            await asyncio.sleep(WALLET_CHECK_INTERVAL)

    async def run(self):
        logger.info("🚀 Worker started")
        await self.send_telegram("✅ **All-in-One-DeFi-Bot worker is online.**")

        try:
            await asyncio.gather(
                self.heartbeat(),
                self.poll_dexscreener(),
                self.monitor_wallet(),
            )
        except asyncio.CancelledError:
            pass
        finally:
            logger.info("🛑 Worker stopped")


if __name__ == "__main__":
    worker = WorkerLoop()
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
