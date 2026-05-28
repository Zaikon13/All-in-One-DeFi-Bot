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

async def get_new_cronos_pairs(known_pairs: set, limit: int = 5) -> list[dict]:
    """
    Fetch latest pairs on Cronos and return only new ones not in known_pairs.
    Updates known_pairs in-place with newly seen pair addresses.
    """
    url = "https://api.dexscreener.com/latest/dex/search?q=cronos"
    new_pairs = []

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return []

            data = resp.json()
            pairs = data.get("pairs", []) or []

            for pair in pairs:
                pair_address = pair.get("pairAddress")
                if not pair_address or pair_address in known_pairs:
                    continue

                # Mark as known immediately
                known_pairs.add(pair_address)

                base = pair.get("baseToken", {})
                quote = pair.get("quoteToken", {})

                new_pairs.append({
                    "pairAddress": pair_address,
                    "baseSymbol": base.get("symbol", "???"),
                    "quoteSymbol": quote.get("symbol", "???"),
                    "priceUsd": pair.get("priceUsd"),
                    "liquidityUsd": pair.get("liquidity", {}).get("usd"),
                    "fdv": pair.get("fdv"),
                    "volume24h": pair.get("volume", {}).get("h24"),
                    "url": f"https://dexscreener.com/cronos/{pair_address}",
                })

                if len(new_pairs) >= limit:
                    break

    except Exception as e:
        print(f"DexScreener new pairs error: {e}")

    return new_pairs