# worker.py - Stable Worker Loop

import asyncio
import logging
from datetime import datetime
import os

import httpx

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")

HEARTBEAT_INTERVAL = 3600
DEXSCREENER_INTERVAL = 300

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("worker")


class WorkerLoop:
    def __init__(self):
        self.running = True

    async def send_telegram(self, text: str):
        if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"})
        except Exception as e:
            logger.error(f"Telegram error: {e}")

    async def heartbeat(self):
        while self.running:
            ts = datetime.now().strftime("%H:%M")
            msg = f"💓 **Worker Heartbeat**\n\n**Time:** {ts}\n**Status:** Online\n**Next:** in 1 hour"
            await self.send_telegram(msg)
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def poll_dexscreener(self):
        while self.running:
            try:
                url = "https://api.dexscreener.com/latest/dex/search?q=cronos"
                async with httpx.AsyncClient(timeout=15) as client:
                    r = await client.get(url)
                    if r.status_code == 200:
                        logger.info("Dexscreener poll OK")
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
        finally:
            logger.info("🛑 Worker stopped")


if __name__ == "__main__":
    worker = WorkerLoop()
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
