# Review Agent 2026-06-09: Standalone test script for Phase 1 current price enrichment display.
# Purpose: Validate that position_value_usd, avg_cost_usd, and total_portfolio_value_usd
# are correctly rendered in both formatters when present in the enriched data.
# This is purely for formatting validation - no real data fetching, no API keys, no DB.
# Run with: python tests/test_phase1_enrichment.py (from project root)

import os
import sys

# Ensure we can import from project root without installation
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set dummy environment variables *before* importing pnl_calculator.
# This prevents the module-level raises for missing API keys (COVALENT/ETHERSCAN)
# and makes the test fully standalone as requested.
os.environ.setdefault("WALLET_ADDRESS", "0x1234567890abcdef1234567890abcdef12345678")
os.environ.setdefault("COVALENT_API_KEY", "dummy-for-test")
os.environ.setdefault("ETHERSCAN_API_KEY", "dummy-for-test")

from core.pnl_calculator import format_pnl_report, format_daily_pnl_report

def create_sample_enriched_data():
    """Create minimal sample data that mimics what _enrich_with_current_prices produces in Phase 1.
    - Includes tokens with and without price enrichment (to test optionality).
    - Uses realistic-ish numbers for Cronos tokens.
    - Provides the required structure for both formatters.
    """
    return {
        "date": "2026-06-09",
        "tokens": [
            {
                "symbol": "CRO",
                "trades": 12,
                "net": 1250.75,
                "trades_list": [
                    {"time": "14:32", "type": "BUY", "amount": 500.0, "symbol": "CRO"},
                    {"time": "15:10", "type": "SELL", "amount": 200.0, "symbol": "CRO"},
                    # ... (truncated for test; real data would have more)
                ],
                # Phase 1 enrichment fields (additive)
                "position_value_usd": 106.31,
                "avg_cost_usd": 0.0851,
                "has_price_data": True,
            },
            {
                "symbol": "USDC",
                "trades": 3,
                "net": -250.0,
                "trades_list": [
                    {"time": "09:15", "type": "SELL", "amount": 250.0, "symbol": "USDC"},
                ],
                # This token has price data but no buys in the day's list → no avg_cost_usd
                "position_value_usd": 250.0,
                "has_price_data": True,
                # Note: avg_cost_usd intentionally absent to test optional rendering
            },
            {
                "symbol": "WETH",
                "trades": 0,
                "net": 0.0,
                "trades_list": [],
                # No price data for this token → should not show USD sections
            },
        ],
        # Root-level aggregate from enrichment (additive)
        "total_portfolio_value_usd": 356.31,
    }

def main():
    print("=" * 60)
    print("PHASE 1 ENRICHMENT FORMATTER VALIDATION")
    print("Review Agent 2026-06-09: This script exercises only the display layer.")
    print("=" * 60)

    sample_data = create_sample_enriched_data()

    report1 = format_pnl_report(sample_data)
    # Simulate a Grok insight (the formatter will append it)
    fake_insight = "The portfolio showed positive rotation in native tokens with stable USD positioning."
    report2 = format_daily_pnl_report(sample_data, fake_insight)

    # Write to UTF-8 file to avoid console encoding issues (e.g. cp1253 on Windows)
    # This ensures the full output with emojis and new USD sections is captured reliably.
    output_path = "phase1_validation_output.txt"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("PHASE 1 ENRICHMENT FORMATTER VALIDATION\n")
        f.write("Review Agent 2026-06-09: This script exercises only the display layer.\n")
        f.write("=" * 60 + "\n\n")

        f.write("--- format_pnl_report (legacy / fallback path) ---\n")
        f.write(report1 + "\n\n")

        f.write("--- format_daily_pnl_report (production path with Grok insight) ---\n")
        f.write(report2 + "\n\n")

        f.write("=" * 60 + "\n")
        f.write("Validation complete. Check above output for:\n")
        f.write("- Per-token 'Position Value (USD)' and 'Avg Cost (USD)' where applicable\n")
        f.write("- 'Total Portfolio Value (USD)' at root level\n")
        f.write("- No new sections for tokens without price data\n")
        f.write("=" * 60 + "\n")

    print(f"Output written to {output_path} (UTF-8).")
    print("Run 'type phase1_validation_output.txt' or 'cat phase1_validation_output.txt' to view.")

if __name__ == "__main__":
    main()