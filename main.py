# main.py
from __future__ import annotations

import os
import time
import logging
from datetime import datetime

import schedule
import httpx

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TZ = os.getenv("TZ", "UTC")

def bot_api(method: str) -> str:
    if not BOT_TOKEN:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")
    return f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

def send_telegram(text: str) -> None:
    if not (BOT_TOKEN and CHAT_ID):
        logging.warning("Skipping Telegram send (missing token or chat id)")
        return
    try:
        with httpx.Client(timeout=10) as client:
            client.post(
                bot_api("sendMessage"),
                json={"chat_id": int(CHAT_ID), "text": text},
            )
    except Exception as e:
        logging.exception("Telegram send failed: %s", e)

def job_heartbeat():
    now = datetime.now().strftime("%H:%M:%S")
    send_telegram(f"⏱️ Worker heartbeat ({now})")

def run_forever():
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting Worker (TZ=%s)", TZ)
    send_telegram("✅ All-in-One-DeFi-Bot worker is online.")

    # === ΕΔΩ θα προσθέσουμε αργότερα Dexscreener polls, wallet monitor κ.λπ. ===
    schedule.every(30).minutes.do(job_heartbeat)

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    run_forever()
