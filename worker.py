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

MONITORED_TOKENS = {
    # Add your tokens here, example:
    # "0x...Mery...": "MERY",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("worker")


class WorkerLoop:
    def __init__(self):
        self.running = True
        self.last_balance = None
        self.last_token_balances = {}
        self.known_pairs = set()  # For new pair detection

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

    # ==================== IMPROVED DEXSCREENER (New Pairs) ====================
    async def poll_dexscreener(self):
        while self.running:
            try:
                url = "https://api.dexscreener.com/latest/dex/pairs/cronos"
                async with httpx.AsyncClient(timeout=15) as client:
                    r = await client.get(url)
                    if r.status_code == 200:
                        data = r.json()
                        pairs = data.get("pairs", [])

                        new_pairs_found = []
                        for pair in pairs:
                            pair_id = pair.get("pairAddress")
                            if pair_id and pair_id not in self.known_pairs:
                                self.known_pairs.add(pair_id)
                                new_pairs_found.append(pair)

                        # Send alert for new pairs (limit to 2 per check)
                        for pair in new_pairs_found[:2]:
                            base = pair.get("baseToken", {})
                            quote = pair.get("quoteToken", {})
                            msg = (
                                f"🚀 **New Pair Detected on Cronos**\n\n"
                                f"**Token:** {base.get('symbol', 'Unknown')}\n"
                                f"**Pair:** {base.get('symbol')}/{quote.get('symbol')}\n"
                                f"**Price:** ${pair.get('priceUsd', 'N/A')}\n"
                                f"**Liquidity:** ${pair.get('liquidity', {}).get('usd', 0):,.0f}\n"
                                f"**Link:** https://dexscreener.com/cronos/{pair.get('pairAddress')}\n"
                            )
                            await self.send_telegram(msg)
                            logger.info(f"New pair alert sent: {base.get('symbol')}")

            except Exception as e:
                logger.error(f"Dexscreener error: {e}")

            await asyncio.sleep(DEXSCREENER_INTERVAL)

    # ==================== REAL WALLET + ERC-20 ====================
    async def monitor_wallet(self):
        if not WALLET_ADDRESS:
            await asyncio.sleep(WALLET_CHECK_INTERVAL)
            return

        while self.running:
            try:
                # Native CRO
                payload = {
                    "jsonrpc": "2.0", "method": "eth_getBalance",
                    "params": [WALLET_ADDRESS, "latest"], "id": 1
                }
                async with httpx.AsyncClient(timeout=15) as client:
                    r = await client.post(CRONOS_RPC, json=payload)
                    if r.status_code == 200:
                        hex_balance = r.json().get("result", "0x0")
                        balance_cro = int(hex_balance, 16) / 10**18

                        if self.last_balance is not None and abs(balance_cro - self.last_balance) > 0.1:
                            diff = balance_cro - self.last_balance
                            msg = f"💰 **CRO Balance Changed**\n\n**New:** {balance_cro:.4f} CRO\n**Change:** {diff:+.4f} CRO"
                            await self.send_telegram(msg)

                        self.last_balance = balance_cro

                # ERC-20 Tokens
                for token_address, symbol in MONITORED_TOKENS.items():
                    data = "0x70a08231000000000000000000000000" + WALLET_ADDRESS[2:].zfill(40)
                    payload = {
                        "jsonrpc": "2.0",
                        "method": "eth_call",
                        "params": [{"to": token_address, "data": data}, "latest"],
                        "id": 1
                    }
                    r = await client.post(CRONOS_RPC, json=payload)
                    if r.status_code == 200:
                        hex_bal = r.json().get("result", "0x0")
                        balance = int(hex_bal, 16) / 10**18

                        last = self.last_token_balances.get(symbol)
                        if last is not None and abs(balance - last) > 0.0001:
                            diff = balance - last
                            msg = f"💰 **{symbol} Balance Changed**\n\n**New:** {balance:.6f} {symbol}\n**Change:** {diff:+.6f} {symbol}"
                            await self.send_telegram(msg)

                        self.last_token_balances[symbol] = balance

            except Exception as e:
                logger.error(f"Wallet error: {e}")

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
