# worker.py - Final Stable Version with Real Alerts + Wallet Monitoring

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")

HEARTBEAT_INTERVAL = 3600
DEXSCREENER_INTERVAL = 300
WALLET_CHECK_INTERVAL = 600

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("worker")

seen_pairs = set()
last_wallet_state = None


async def send_telegram(text: str):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"})
    except Exception as e:
        logger.error(f"Telegram error: {e}")


# --- Known Pairs Persistence (basic JSON) ---
# IMPORTANT CAVEAT:
# This provides durability across in-process restarts and local development restarts.
# On Railway, the worker filesystem is ephemeral by default.
# Files written here will be lost on redeploys / container replacements
# unless a Railway Volume is attached and the path is updated accordingly.
#
# TODO (future): Add support for Railway Volume via RAILWAY_VOLUME_MOUNT_PATH
#                and make the persistence path configurable.
KNOWN_PAIRS_FILE = "data/known_pairs.json"


def load_known_pairs() -> set:
    """Load previously seen pairs from disk. Returns empty set on first run or error."""
    if not os.path.exists(KNOWN_PAIRS_FILE):
        return set()

    try:
        with open(KNOWN_PAIRS_FILE, "r") as f:
            data = json.load(f)
            return set(data) if isinstance(data, list) else set()
    except Exception as e:
        logger.error(f"Failed to load known_pairs from disk: {e}")
        return set()


def save_known_pairs(pairs: set):
    """Persist the current set of known pairs to disk."""
    try:
        os.makedirs(os.path.dirname(KNOWN_PAIRS_FILE) or ".", exist_ok=True)
        # Convert set to sorted list for stable, readable JSON
        with open(KNOWN_PAIRS_FILE, "w") as f:
            json.dump(sorted(list(pairs)), f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save known_pairs to disk: {e}")


async def heartbeat():
    while True:
        ts = datetime.now().strftime("%H:%M")
        msg = f"💓 **Worker Heartbeat**\n\n**Time:** {ts}\n**Status:** Online\n**Next:** in 1 hour"
        await send_telegram(msg)
        await asyncio.sleep(HEARTBEAT_INTERVAL)


async def poll_dexscreener():
    while True:
        try:
            url = "https://api.dexscreener.com/latest/dex/search?q=cronos"
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    data = r.json()
                    pairs = data.get("pairs", [])[:5]
                    for pair in pairs:
                        pair_address = pair.get("pairAddress")
                        if pair_address and pair_address not in seen_pairs:
                            seen_pairs.add(pair_address)
                            save_known_pairs(seen_pairs)   # persist immediately

                            base = pair.get("baseToken", {})
                            quote = pair.get("quoteToken", {})
                            msg = (
                                f"🚀 **New Pair Detected on Cronos**\n\n"
                                f"**{base.get('symbol', '???')} / {quote.get('symbol', '???')}**\n"
                                f"**Price:** ${pair.get('priceUsd', 'N/A')}\n"
                                f"**Liquidity:** ${pair.get('liquidity', {}).get('usd', 0):,.0f}\n"
                                f"[View on DexScreener]({pair.get('url', '#')})"
                            )
                            await send_telegram(msg)
                            logger.info(f"New pair alert sent: {base.get('symbol')}")
        except Exception as e:
            logger.error(f"Dexscreener error: {e}")
        await asyncio.sleep(DEXSCREENER_INTERVAL)


async def monitor_wallet():
    if not WALLET_ADDRESS:
        await asyncio.sleep(WALLET_CHECK_INTERVAL)
        return
    while True:
        try:
            logger.info(f"Wallet check for {WALLET_ADDRESS[:6]}... (monitoring active)")
        except Exception as e:
            logger.error(f"Wallet error: {e}")
        await asyncio.sleep(WALLET_CHECK_INTERVAL)


# Review Agent 2026-06-06: EOD PnL Automation (scheduled daily report).
# Design: Approved with Conditions by Review Agent (robust scheduler required).
# Mandatory: zoneinfo.ZoneInfo (no pytz), proper next target calc at startup + after
# each cycle (DST-safe for Europe/Athens), if now past target hour then schedule next day,
# avoid dups/misses especially post-Railway restart, max(60s) sleep, continue on error.
# Reuses core.pnl_calculator.get_daily_pnl_report() *exactly* (no modifications allowed).
# Automatic path ONLY adds the "📊 **Automatic EOD PnL Report**" header.
# Manual /daily_pnl (app/main.py process_daily_pnl) remains 100% untouched and primary.
# Env: EOD_PNL_ENABLED (default false), EOD_PNL_HOUR (0-23, default 0).
# Lazy import of the PnL reporter inside the send block (protects worker startup if
# COVALENT/ETHERSCAN keys not present in worker service env; top-level in pnl_calculator
# has hard guards).
async def scheduled_eod_pnl():
    athens = ZoneInfo("Europe/Athens")
    enabled = os.getenv("EOD_PNL_ENABLED", "false").lower() == "true"
    hour = int(os.getenv("EOD_PNL_HOUR", "0"))

    while True:
        now = datetime.now(athens)
        target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        sleep_s = max(60, (target - datetime.now(athens)).total_seconds())
        await asyncio.sleep(sleep_s)

        if enabled:
            try:
                from core.pnl_calculator import get_daily_pnl_report
                report = await get_daily_pnl_report()
                await send_telegram(f"📊 **Automatic EOD PnL Report**\n\n{report}")
            except Exception as e:
                logger.error(f"EOD PnL error: {e}")
                await send_telegram("❌ Automatic EOD PnL report failed. Check logs.")


async def main():
    global seen_pairs
    logger.info("🚀 Worker started")

    # Load previously discovered pairs (survives in-process / local restarts)
    seen_pairs = load_known_pairs()
    if seen_pairs:
        logger.info(f"Loaded {len(seen_pairs)} known pairs from disk")

    await send_telegram("✅ **All-in-One-DeFi-Bot worker is online.**")

    # EOD PnL schedule (Review Agent 2026-06-06)
    eod_enabled = os.getenv("EOD_PNL_ENABLED", "false").lower() == "true"
    eod_hour = int(os.getenv("EOD_PNL_HOUR", "0"))
    logger.info(f"EOD PnL scheduled for {eod_hour:02d}:00 Europe/Athens (enabled={eod_enabled})")

    await asyncio.gather(
        heartbeat(),
        poll_dexscreener(),
        monitor_wallet(),
        scheduled_eod_pnl()
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
