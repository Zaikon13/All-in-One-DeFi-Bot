"""
core/market_analysis.py - Thin helper for programmatic Grok Token/Market Analysis (runtime only).

Strictly reuses core/grok_client.py SOT (load_prompt + call_grok + is_valid_grok_response).
Pre-compute all data in caller (Python); this module only prepares compact prompt input and returns qualitative insight.
Analysis/summarization/insights ONLY - no trading decisions or execution language (per contract).

Usage pattern (exact match to PnL/grok-analyze):
- Caller builds summaries (pair data, market snapshots, etc.).
- Call get_market_insight(...) with timeout.
- Check is_valid_grok_response; fallback to raw summary if not.
- Env-gated and logged by caller.

# Review Agent 2026-06: First increment of worker-side Grok market analysis.
# High-risk (worker.py + new Grok site + prompt contract). Must follow full Review Gate.
# Reuses client exclusively. No autonomy. Thin extension of existing runtime patterns.
# See 12 mandatory conditions in reviews/2026-06-XX-grok-market-analysis.md and Primary SOTs.
"""

from core.grok_client import load_prompt, call_grok, is_valid_grok_response
import logging

logger = logging.getLogger(__name__)


async def get_market_insight(
    pair_summary: str,
    market_data_summary: str,
    timeout: float = 25.0,
) -> str:
    """
    Thin wrapper: calls Grok via SOT client for qualitative market/token insight.

    Caller MUST pre-compute all data. This only feeds compact summaries to the prompt.
    Returns raw Grok output (caller must gate with is_valid_grok_response and fallback).
    """
    if not pair_summary and not market_data_summary:
        return ""

    try:
        prompt = load_prompt(
            "grok_market_analysis.txt",
            pair_summary=pair_summary or "N/A",
            market_data_summary=market_data_summary or "N/A",
        )
        insight = await call_grok(prompt, timeout=timeout)
        return insight.strip() if insight else ""
    except Exception as e:
        logger.exception("market_analysis Grok call error")
        return ""


# Convenience for callers that want the gated + fallback behavior in one call.
async def get_market_insight_with_fallback(
    pair_summary: str,
    market_data_summary: str,
    raw_fallback: str = "",
    timeout: float = 25.0,
) -> str:
    """
    Same as get_market_insight but applies is_valid gate + returns fallback if invalid.
    Use this for simple integrations (matches process_grok_analyze / daily_pnl pattern).
    """
    insight = await get_market_insight(pair_summary, market_data_summary, timeout=timeout)
    if is_valid_grok_response(insight):
        return insight
    logger.info("Grok market insight low-quality or failed; using fallback")
    return raw_fallback or ""