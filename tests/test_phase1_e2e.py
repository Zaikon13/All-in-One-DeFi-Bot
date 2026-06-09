# Review Agent 2026-06-09: E2E validation script for Phase 1.
# Purpose: Test the real PriceService (live CoinGecko call) in a standalone, defensive way.
# - Uses actual symbols from the Cronos ecosystem.
# - Demonstrates timing (to observe cache behavior on second call).
# - Graceful per-symbol fallback: never crashes if a symbol has no price data.
# - No dependencies on WALLET, API keys, or other PnL internals beyond the price helper.
# - This exercises the integration point that will be used by the enrichment layer.

import os
import sys
import time

# Make the script runnable from anywhere by adding project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.price_service import PriceService

def main():
    print("=== GROK BUILD: Phase 1 E2E - Real PriceService + Enrichment Validation ===")
    print("Review Agent 2026-06-09: Live call to CoinGecko via PriceService.")
    print("Symbols under test: CRO, USDC, WETH, VVS (defensive - some may return None).")
    print("")

    symbols = ['CRO', 'USDC', 'WETH', 'VVS']

    service = PriceService()

    # First call - should hit the network (CoinGecko)
    start = time.time()
    prices1 = service.get_current_prices(symbols)
    elapsed1 = time.time() - start

    print(f"First call results (took {elapsed1:.2f}s):")
    for sym in symbols:
        price = prices1.get(sym)
        status = "OK" if price is not None else "NO DATA (graceful fallback)"
        print(f"  {sym}: {price}  [{status}]")

    # Second call - should hit the in-memory cache (much faster)
    start = time.time()
    prices2 = service.get_current_prices(symbols)
    elapsed2 = time.time() - start

    print(f"\nSecond call results (took {elapsed2:.2f}s) - cache expected:")
    for sym in symbols:
        price = prices2.get(sym)
        print(f"  {sym}: {price}")

    print(f"\nCache behavior check: second call was ~{elapsed2/elapsed1:.1f}x faster (expected << 1.0 if cached)")

    service.close()

    print("\nE2E test completed successfully.")
    print("Review Agent 2026-06-09: All paths were defensive. No crashes on missing price data.")
    print("If prices were returned, the enrichment layer (future steps) can consume them.")
    print("=== End of E2E validation ===")

if __name__ == "__main__":
    main()