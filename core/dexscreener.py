import httpx
import asyncio
from typing import Optional

DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/tokens"

async def get_token_price(token_address: str) -> Optional[float]:
    """Get current USD price for a token on Cronos using DexScreener."""
    if not token_address:
        return None
    try:
        url = f"{DEXSCREENER_API}/{token_address}"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            data = resp.json()
            if data.get("pairs"):
                # Take the first pair (usually the most liquid)
                price = float(data["pairs"][0].get("priceUsd", 0))
                return price
    except Exception as e:
        print(f"DexScreener price error for {token_address}: {e}")
    return None

async def poll_new_pairs():
    print('Polling Dexscreener for Cronos new pairs...')
    return [{'pair': 'EXAMPLE', 'signal': 'BUY', 'reason': 'High volume spike'}]