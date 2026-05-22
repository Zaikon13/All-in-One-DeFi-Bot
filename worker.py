# worker.py - All-in-One-DeFi-Bot Worker Loop

import asyncio
import logging
from datetime import datetime
import os

import httpx

# ==================== CONFIGURATION ====================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")

HEARTBEAT_INTERVAL = 3600
DEXSCREENER_INTERVAL = 300
WALLET_CHECK_INTERVAL = 600

CRONOS_RPC = "https://evm.cronos.org"

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("worker")


class WorkerLoop:
    def __init__(self):
        self.running = True
        self.last_balance = None

    async def send_telegram(self, text: str):
        if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"})
        except Exception as e:
            logger.error(f"Telegram error: {e}")

    # ==================== HEARTBEAT ====================
    async def heartbeat(self):
        while self.running:
            ts = datetime.now().strftime("%H:%M")
            msg = f"💓 **Worker Heartbeat**\n\n**Time:** {ts}\n**Status:** Online\n**Next:** in 1 hour"
            await self.send_telegram(msg)
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    # ==================== DEXSCREENER ====================
    async def poll_dexscreener(self):
        while self.running:
            try:
                url = "https://api.dexscreener.com/latest/dex/pairs/cronos"
                async with httpx.AsyncClient(timeout=15) as client:
                    r = await client.get(url)
                    if r.status_code == 200:
                        logger.info("Dexscreener poll OK")
            except Exception as e:
                logger.error(f"Dexscreener error: {e}")
            await asyncio.sleep(DEXSCREENER_INTERVAL)

    # ==================== REAL WALLET MONITORING ====================
    async def monitor_wallet(self):
        """Check native CRO balance on Cronos"""
        if not WALLET_ADDRESS:
            await asyncio.sleep(WALLET_CHECK_INTERVAL)
            return

        while self.running:
            try:
                # Get native CRO balance
                payload = {
                    "jsonrpc": "2.0",
                    "method": "eth_getBalance",
                    "params": [WALLET_ADDRESS, "latest"],
                    "id": 1
                }
                async with httpx.AsyncClient(timeout=15) as client:
                    r = await client.post(CRONOS_RPC, json=payload)
                    if r.status_code == 200:
                        data = r.json()
                        hex_balance = data.get("result", "0x0")
                        balance_wei = int(hex_balance, 16)
                        balance_cro = balance_wei / 10**18

                        # Send alert if balance changed significantly
                        if self.last_balance is not None:
                            diff = balance_cro - self.last_balance
                            if abs(diff) > 0.1:  # Alert if change > 0.1 CRO
                                msg = f"💰 **Wallet Alert**\n\n**Address:** `{WALLET_ADDRESS[:6]}...{WALLET_ADDRESS[-4:]}`\n**New Balance:** {balance_cro:.4f} CRO\n**Change:** {diff:+.4f} CRO"
                                await self.send_telegram(msg)

                        self.last_balance = balance_cro
                        logger.info(f"Wallet balance: {balance_cro:.4f} CRO")

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
                self.monitor_wallet()
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
