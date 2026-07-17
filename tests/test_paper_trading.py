# Paper-trading engine (2026-07-17) — offline unit tests for the pure decision
# logic, PnL math, and state I/O. SIMULATION ONLY; no network anywhere here.

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import paper_trading as pt

NOW = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)


def _state(balance=1000.0):
    return {"balance_usd": balance, "starting_usd": 1000.0, "open": [], "closed": []}


class TestShouldEnter(unittest.TestCase):
    def A(self, **kw):
        d = dict(score=75, price=0.01, open_count=0, balance_usd=1000.0,
                 already_open=False, entry_score=70, position_usd=50, max_open=5)
        d.update(kw)
        return pt.should_enter(d["score"], d["price"], d["open_count"],
                               d["balance_usd"], d["already_open"],
                               d["entry_score"], d["position_usd"], d["max_open"])

    def test_fire_tier_enters(self):
        ok, _ = self.A()
        self.assertTrue(ok)

    def test_below_bar_rejected(self):
        ok, why = self.A(score=69.9)
        self.assertFalse(ok); self.assertIn("below entry bar", why)

    def test_duplicate_pair_rejected(self):
        ok, why = self.A(already_open=True)
        self.assertFalse(ok); self.assertIn("already", why)

    def test_max_open_rejected(self):
        ok, why = self.A(open_count=5)
        self.assertFalse(ok); self.assertIn("max open", why)

    def test_insufficient_balance_rejected(self):
        ok, why = self.A(balance_usd=49.99)
        self.assertFalse(ok); self.assertIn("insufficient", why)

    def test_bad_price_and_nan_rejected(self):
        for bad in (0, -1, "nan", "inf", None, "junk"):
            ok, why = self.A(price=bad)
            self.assertFalse(ok, f"price={bad}")
        ok, _ = self.A(score="nan")
        self.assertFalse(ok)


class TestOpenClose(unittest.TestCase):
    def test_open_debits_balance_and_computes_qty(self):
        st = _state()
        pos = pt.open_position(st, "0xPAIR", "WOOF/WCRO", "0xTOK", 0.002, 72.4,
                               NOW.isoformat(), position_usd=50)
        self.assertAlmostEqual(st["balance_usd"], 950.0)
        self.assertAlmostEqual(pos["qty"], 25000.0)
        self.assertEqual(len(st["open"]), 1)

    def test_close_tp_credits_profit(self):
        st = _state()
        pos = pt.open_position(st, "0xp", "A/B", "0xt", 0.002, 71, NOW.isoformat(), 50)
        closed = pt.close_position(st, pos, 0.0025, "take-profit", NOW.isoformat())
        self.assertAlmostEqual(closed["pnl_usd"], 12.5)
        self.assertAlmostEqual(closed["pnl_pct"], 25.0)
        self.assertAlmostEqual(st["balance_usd"], 1012.5)
        self.assertEqual(st["open"], [])
        self.assertEqual(len(st["closed"]), 1)

    def test_close_sl_books_loss(self):
        st = _state()
        pos = pt.open_position(st, "0xp", "A/B", "0xt", 0.002, 71, NOW.isoformat(), 50)
        closed = pt.close_position(st, pos, 0.0017, "stop-loss", NOW.isoformat())
        self.assertAlmostEqual(closed["pnl_usd"], -7.5)
        self.assertAlmostEqual(st["balance_usd"], 992.5)

    def test_win_rate_and_equity_pnl(self):
        st = _state()
        p1 = pt.open_position(st, "0xa", "A/B", "0xta", 0.002, 71, NOW.isoformat(), 50)
        pt.close_position(st, p1, 0.0025, "take-profit", NOW.isoformat())
        p2 = pt.open_position(st, "0xb", "C/D", "0xtb", 1.0, 71, NOW.isoformat(), 50)
        pt.close_position(st, p2, 0.85, "stop-loss", NOW.isoformat())
        self.assertAlmostEqual(pt.win_rate(st), 50.0)
        self.assertAlmostEqual(pt.total_equity_pnl(st), 12.5 - 7.5)
        self.assertIsNone(pt.win_rate(_state()))


class TestCheckExit(unittest.TestCase):
    def P(self, entry=0.002, opened=NOW - timedelta(hours=1)):
        return {"entry_price": entry, "opened_at": opened.isoformat(),
                "qty": 25000, "usd_in": 50, "symbol": "A/B", "pair_address": "0xp"}

    def test_tp_hit(self):
        r = pt.check_exit(self.P(), 0.0026, NOW, 25, 15, 24)
        self.assertEqual(r[0], "take-profit")

    def test_sl_hit(self):
        r = pt.check_exit(self.P(), 0.0016, NOW, 25, 15, 24)
        self.assertEqual(r[0], "stop-loss")

    def test_hold_inside_band(self):
        self.assertIsNone(pt.check_exit(self.P(), 0.0021, NOW, 25, 15, 24))

    def test_time_stop_with_price(self):
        pos = self.P(opened=NOW - timedelta(hours=25))
        r = pt.check_exit(pos, 0.00201, NOW, 25, 15, 24)
        self.assertEqual(r[0], "time-stop")

    def test_missing_price_never_exits_even_past_time(self):
        pos = self.P(opened=NOW - timedelta(hours=48))
        self.assertIsNone(pt.check_exit(pos, None, NOW, 25, 15, 24))
        self.assertIsNone(pt.check_exit(pos, "nan", NOW, 25, 15, 24))
        self.assertIsNone(pt.check_exit(pos, 0, NOW, 25, 15, 24))

    def test_tp_beats_time_stop(self):
        pos = self.P(opened=NOW - timedelta(hours=30))
        r = pt.check_exit(pos, 0.0030, NOW, 25, 15, 24)
        self.assertEqual(r[0], "take-profit")


class TestStateIO(unittest.TestCase):
    def test_missing_file_gives_fresh_state(self):
        st = pt.load_state("/nonexistent/dir/paper_state.json")
        self.assertEqual(st["balance_usd"], st["starting_usd"])
        self.assertEqual(st["open"], [])

    def test_corrupt_file_degrades_to_fresh(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("{not json")
            p = f.name
        try:
            st = pt.load_state(p)
            self.assertEqual(st["open"], [])
        finally:
            os.unlink(p)

    def test_roundtrip(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "paper_state.json")
        st = _state()
        pos = pt.open_position(st, "0xp", "A/B", "0xt", 0.5, 71, NOW.isoformat(), 50)
        self.assertTrue(pt.save_state(st, p))
        st2 = pt.load_state(p)
        self.assertAlmostEqual(st2["balance_usd"], 950.0)
        self.assertEqual(st2["open"][0]["pair_address"], "0xp")

    def test_malformed_open_positions_dropped_on_load(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "paper_state.json")
        bad = {"balance_usd": 900, "starting_usd": 1000, "closed": [],
               "open": [
                   {"pair_address": "0xok", "token_address": "0xt", "entry_price": 0.1,
                    "qty": 500.0, "usd_in": 50.0, "symbol": "OK/X", "opened_at": "2026-07-17T00:00:00+00:00"},
                   {"pair_address": "0xzombie"},          # missing everything
                   "not-a-dict",
                   {"pair_address": "0xnan", "token_address": "0xt", "entry_price": float("nan"),
                    "qty": 1, "usd_in": 1},
               ]}
        json.dump(bad, open(p, "w"))
        st = pt.load_state(p)
        self.assertEqual([q["pair_address"] for q in st["open"]], ["0xok"])
        # int balance accepted (not silently reset to the default 1000)
        self.assertEqual(st["balance_usd"], 900.0)

    def test_summary_line_formats(self):
        st = _state()
        line = pt.paper_summary_line(st)
        self.assertIn("🧪 Paper: balance $1,000.00", line)
        self.assertIn("win rate —", line)
        self.assertNotIn("\n", line)


if __name__ == "__main__":
    unittest.main()
