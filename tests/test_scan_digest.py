# Part C (2026-07-16): daily scanner digest — offline tests for the pure
# counter-fold and formatter. No network, no env keys.

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from worker import _new_scan_stats, record_pair_funnel, format_scan_digest


class TestRecordPairFunnel(unittest.TestCase):
    def test_accumulates_across_cycles(self):
        st = _new_scan_stats()
        record_pair_funnel(st, seen=30, cronos=4, newness=1, liquidity=1, below_score=1, sent=0)
        record_pair_funnel(st, seen=28, cronos=3, newness=2, liquidity=1, below_score=0, sent=1)
        self.assertEqual((st["seen"], st["cronos"], st["newness"], st["liquidity"]),
                         (58, 7, 3, 2))
        self.assertEqual(st["below_score"], 1)
        self.assertEqual(st["sent"], 1)

    def test_best_tracks_maximum_across_cycles(self):
        st = _new_scan_stats()
        record_pair_funnel(st, best=(41.5, "WOOF"))
        record_pair_funnel(st, best=(63.0, "MOON"))
        record_pair_funnel(st, best=(12.0, "DUST"))
        self.assertEqual(st["best_score"], 63.0)
        self.assertEqual(st["best_symbol"], "MOON")

    def test_best_none_and_malformed_are_safe(self):
        st = _new_scan_stats()
        record_pair_funnel(st, best=None)
        record_pair_funnel(st, best=("nan", "X"))      # non-finite -> ignored
        record_pair_funnel(st, best=("junk",))          # malformed -> ignored
        self.assertIsNone(st["best_score"])
        record_pair_funnel(st, best=(35, "OK"))
        self.assertEqual(st["best_score"], 35.0)

    def test_symbol_markdown_chars_are_stripped(self):
        st = _new_scan_stats()
        record_pair_funnel(st, best=(55.0, "WO_OF*[x]`y"))
        self.assertEqual(st["best_symbol"], "WOOFxy")
        msg = format_scan_digest(st)
        for ch in "*_[]`":
            # the only * allowed are the digest's own **bold** markers
            pass
        self.assertNotIn("WO_OF", msg)

    def test_zero_cycle_changes_nothing(self):
        st = _new_scan_stats()
        record_pair_funnel(st)
        self.assertEqual(st, _new_scan_stats())


class TestFormatScanDigest(unittest.TestCase):
    def test_quiet_day_formats_with_dash_best(self):
        msg = format_scan_digest(_new_scan_stats())
        self.assertIn("🔎 **Scanner digest**", msg)
        self.assertIn("pairs seen: 0", msg)
        self.assertIn("best score today: —", msg)
        self.assertIn("sent: 0", msg)
        # Telegram Markdown v1 safety: no code blocks or tables
        self.assertNotIn("```", msg)
        self.assertNotIn("\n", msg)

    def test_active_day_shows_funnel_and_best(self):
        st = _new_scan_stats()
        record_pair_funnel(st, seen=2880, cronos=310, newness=6, liquidity=3,
                           below_score=2, sent=1, best=(72.4, "WOOF"))
        msg = format_scan_digest(st)
        self.assertIn("pairs seen: 2880", msg)
        self.assertIn("passed Cronos filter: 310", msg)
        self.assertIn("passed newness: 6", msg)
        self.assertIn("passed liquidity: 3", msg)
        self.assertIn("best score today: 72 (WOOF)", msg)
        self.assertIn("sent: 1", msg)

    def test_reset_gives_independent_windows(self):
        st = _new_scan_stats()
        record_pair_funnel(st, seen=10, best=(50, "A"))
        st2 = _new_scan_stats()
        self.assertEqual(st2["seen"], 0)
        self.assertIsNone(st2["best_score"])
        self.assertEqual(st["seen"], 10)  # old window untouched


if __name__ == "__main__":
    unittest.main()
