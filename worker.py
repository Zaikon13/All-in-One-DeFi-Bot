# worker.py - All-in-One-DeFi-Bot Worker Loop

import asyncio
import logging
from datetime import datetime
import os

import httpx

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HEARTBEAT_INTERVAL = 3600  # 1 hour
DEXSCREENER_POLL_INTERVAL = 300  # 5 minutes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("worker")


class WorkerLoop:
    def __init__(self):
        self.running = True
        self.last_heartbeat = None

    async def send_telegram_message(self, text: str):
        if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(url, json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": text,
                    "parse_mode": "Markdown"
                })
        except Exception as e:
            logger.error(f"Telegram error: {e}")

    async def heartbeat(self):
        while self.running:
            timestamp = datetime.now().strftime("%H:%M")
            message = (
                f"💓 **Worker Heartbeat**

"
                f"**Time:** {timestamp}
"
                f"**Status:** Online & Healthy
"
                f"**Next:** in 1 hour"
            )
            await self.send_telegram_message(message)
            self.last_heartbeat = datetime.now()
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def poll_dexscreener(self):
        """Poll Dexscreener for new pairs/tokens (placeholder)"""
        while self.running:
            try:
                # TODO: Add real Dexscreener API call here
                # Example: Check for new pairs or price movements
                logger.info("Dexscreener poll completed (placeholder)")
            except Exception as e:
                logger.error(f"Dexscreener poll error: {e}")
            await asyncio.sleep(DEXSCREENER_POLL_INTERVAL)

    async def run(self):
        logger.info("🚀 Worker started")
        await self.send_telegram_message("✅ **All-in-One-DeFi-Bot worker is online.**")

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
