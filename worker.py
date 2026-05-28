# worker.py - Improved Stable Worker Loop with Real Alerts

import asyncio
import logging
import os
from datetime import datetime

import httpx

# Environment Variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")

# Intervals (seconds)
HEARTBEAT_INTERVAL = 3600      # 1 hour
DEXSCREENER_INTERVAL = 300     # 5 minutes
WALLET_CHECK_INTERVAL = 600    # 10 minutes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("worker")

# Track seen pairs to avoid duplicate alerts
seen_pairs = set()


class WorkerLoop:
    def __init__(self):
        self.running = True

    async def send_telegram(self, text: str):
        if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                await client.post(
                    url,
                    json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
                )
        except Exception as e:
            logger.error(f"Telegram error: {e}")

    async def heartbeat(self):
        while self.running:
            try:
                ts = datetime.now().strftime("%H:%M")
                msg = f"💓 **Worker Heartbeat**\n\n**Time:** {ts}\n**Status:** Online\n**Next:** in 1 hour"
                await self.send_telegram(msg)
                logger.info("Heartbeat sent")
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def poll_dexscreener(self):
        while self.running:
            try:
                url = "https://api.dexscreener.com/latest/dex/search?q=cronos"
                async with httpx.AsyncClient(timeout=20) as client:
                    r = await client.get(url)
                    if r.status_code == 200:
                        data = r.json()
                        pairs = data.get("pairs", [])[:5]  # Top 5 pairs

                        for pair in pairs:
                            pair_address = pair.get("pairAddress")
                            if pair_address and pair_address not in seen_pairs:
                                seen_pairs.add(pair_address)
                                base = pair.get("baseToken", {})
                                symbol = base.get("symbol", "Unknown")
                                price = pair.get("priceUsd", "N/A")
                                liquidity = pair.get("liquidity", {}).get("usd", 0)

                                msg = (
                                    f"🚀 **New Pair Detected on Cronos**\n\n"
                                    f"**Token:** {symbol}\n"
                                    f"**Pair:** {pair.get('quoteToken', {}).get('symbol', 'N/A')}\n"
                                    f"**Price:** ${price}\n"
                                    f"**Liquidity:** ${liquidity:,.0f}\n"
                                    f"[View on Dexscreener]({pair.get('url', '#')})"
                                )
                                await self.send_telegram(msg)
                                logger.info(f"New pair alert sent: {symbol}")
            except Exception as e:
                logger.error(f"Dexscreener error: {e}")
            await asyncio.sleep(DEXSCREENER_INTERVAL)

    async def run(self):
        logger.info("🚀 Worker started")
        await self.send_telegram("✅ **All-in-One-DeFi-Bot worker is online.**")

        try:
            await asyncio.gather(
                self.heartbeat(),
                self.poll_dexscreener()
            )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Worker crashed: {e}")
        finally:
            logger.info("🛑 Worker stopped")


if __name__ == "__main__":
    worker = WorkerLoop()
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
