# Review Agent 2026-06-09: Created as part of Phase 1 current price enrichment for PnL reports.
# Isolated defensive helper. Only current prices via CoinGecko free tier.
# Hard timeout, client-side rate limiting + backoff, short cache, graceful per-token fallback (never raises).
# Usable standalone for unit tests. No historical prices. No changes to _aggregate_pnl or core logic.

import time
import logging
from typing import List, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class _PriceCache:
    """Simple TTL cache for current prices."""
    def __init__(self, ttl_seconds: int = 120):
        self._cache: Dict[str, tuple[float, float]] = {}  # symbol -> (price, timestamp)
        self.ttl = ttl_seconds

    def get(self, symbol: str) -> Optional[float]:
        if symbol in self._cache:
            price, ts = self._cache[symbol]
            if time.time() - ts < self.ttl:
                return price
        return None

    def set(self, symbol: str, price: float) -> None:
        self._cache[symbol] = (price, time.time())


class PriceService:
    """Defensive service for fetching current USD prices.

    Public API:
        get_current_prices(symbols: list[str]) -> dict[str, float | None]
    """

    COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"

    # Minimal mapping for common Cronos ecosystem tokens (symbol upper -> CoinGecko id).
    # Extend as more symbols appear in real trades. Falls back to lowercased symbol as id if unknown.
    ID_MAP: Dict[str, str] = {
        "CRO": "crypto-com-chain",
        "USDC": "usd-coin",
        "USDT": "tether",
        "WETH": "weth",
        "WBTC": "wrapped-bitcoin",
        "DAI": "dai",
    }

    def __init__(
        self,
        timeout: float = 7.0,
        min_call_interval: float = 1.5,
        cache_ttl: int = 120,
    ):
        self.timeout = timeout
        self.min_call_interval = min_call_interval
        self.last_call_time = 0.0
        self.cache = _PriceCache(ttl_seconds=cache_ttl)
        self.client = httpx.Client(timeout=timeout)

    def _map_to_id(self, symbol: str) -> str:
        upper = symbol.upper()
        return self.ID_MAP.get(upper, upper.lower())

    def _respect_rate_limit(self) -> None:
        now = time.time()
        elapsed = now - self.last_call_time
        if elapsed < self.min_call_interval:
            sleep_time = self.min_call_interval - elapsed
            logger.debug(f"Rate limit backoff: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
        self.last_call_time = time.time()

    def get_current_prices(self, symbols: List[str]) -> Dict[str, Optional[float]]:
        """Fetch current USD prices.

        Returns mapping of original symbol (upper) -> price or None on any failure for that symbol.
        Partial results are returned. Never raises for the caller.
        """
        if not symbols:
            return {}

        result: Dict[str, Optional[float]] = {}
        ids_to_fetch: List[str] = []
        id_to_symbol: Dict[str, str] = {}

        for raw_sym in symbols:
            sym = raw_sym.upper()
            if sym in result:
                continue

            cached = self.cache.get(sym)
            if cached is not None:
                result[sym] = cached
                continue

            cg_id = self._map_to_id(sym)
            ids_to_fetch.append(cg_id)
            id_to_symbol[cg_id] = sym
            result[sym] = None  # default: graceful fallback

        if not ids_to_fetch:
            return result

        self._respect_rate_limit()

        params = {
            "ids": ",".join(ids_to_fetch),
            "vs_currencies": "usd",
        }

        try:
            resp = self.client.get(self.COINGECKO_URL, params=params)
            if resp.status_code != 200:
                logger.warning(f"CoinGecko non-200 status: {resp.status_code}")
                return result

            data = resp.json() or {}
            for cg_id, price_info in data.items():
                if cg_id in id_to_symbol:
                    sym = id_to_symbol[cg_id]
                    price = price_info.get("usd")
                    if price is not None:
                        try:
                            result[sym] = float(price)
                            self.cache.set(sym, float(price))
                        except (ValueError, TypeError):
                            result[sym] = None
        except httpx.TimeoutException:
            logger.warning("CoinGecko timeout - graceful fallback to None for requested symbols")
        except Exception as exc:
            logger.warning(f"CoinGecko unexpected error: {exc} - graceful fallback to None")

        return result

    def close(self) -> None:
        """Close underlying HTTP client (for cleanup in long-running contexts)."""
        try:
            self.client.close()
        except Exception:
            pass


# Standalone usage example (for manual testing / docs)
if __name__ == "__main__":
    svc = PriceService()
    prices = svc.get_current_prices(["CRO", "USDC", "FAKE123"])
    print("Prices:", prices)
    svc.close()
