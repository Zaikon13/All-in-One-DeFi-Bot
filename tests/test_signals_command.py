# /signals renderer (2026-07-23) — offline. No network.

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
from app.commands.signals import render_signals

NOW = datetime(2026, 7, 23, 20, 0, tzinfo=timezone.utc)


def _sig(recent=None, as_of=None):
    return {
        "chains": ["cro", "solana", "sui-network"],
        "thresholds": {"cro": {"min_liq": 5000.0, "min_score": 35.0},
                       "solana": {"min_liq": 10000.0, "min_score": 35.0},
                       "sui-network": {"min_liq": 10000.0, "min_score": 35.0}},
        "funnel": {"cro": {"seen": 5, "matured": 3, "passed": 0, "sent": 0},
                   "solana": {"seen": 20, "matured": 14, "passed": 2, "sent": 2},
                   "sui-network": {"seen": 20, "matured": 18, "passed": 1, "sent": 1}},
        "recent": recent if recent is not None else [
            {"chain": "solana", "symbol": "MOON", "quote": "SOL", "dex": "raydium",
             "score": 71, "tier": "🔥", "age_h": 1.2, "liquidity": 25000, "vol1h": 8000,
             "buys": 40, "sells": 12, "ts": NOW.isoformat()},
        ],
        "as_of": (as_of or NOW).isoformat(),
    }


class TestRenderSignals(unittest.TestCase):
    def test_no_mirror_says_syncing(self):
        out = render_signals(None, now_utc=NOW)
        self.assertIn("syncing", out.lower())
        self.assertIn("🔎", out)

    def test_thresholds_and_recent_rendered(self):
        out = render_signals(_sig(), now_utc=NOW)
        self.assertIn("Enabled:", out)
        self.assertIn("cro (liq ≥ $5,000, score ≥ 35", out)
        self.assertIn("🔥 **MOON/SOL** score 71", out)
        self.assertIn("raydium", out)
        self.assertIn("Funnel (this window):", out)
        self.assertIn("solana: seen 20/matured 14/passed 2/sent 2", out)

    def test_honest_when_nothing_qualifies(self):
        out = render_signals(_sig(recent=[]), now_utc=NOW)
        # each chain shows its funnel-based 'none this window' line, no fabrication
        self.assertIn("none this window (seen 5, matured 3, passed 0)", out)
        self.assertNotIn("🔥 **", out)

    def test_stale_mirror_flagged(self):
        out = render_signals(_sig(as_of=NOW - timedelta(minutes=45)), now_utc=NOW)
        self.assertIn("45 min old", out)

    def test_markdown_no_codeblocks(self):
        out = render_signals(_sig(), now_utc=NOW)
        self.assertNotIn("```", out)


if __name__ == "__main__":
    unittest.main()
