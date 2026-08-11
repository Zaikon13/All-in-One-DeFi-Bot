"""Paper-trading integrity fix (2026-08-10).

Root cause of the inflated balance: exits booked at the observed price tick with
no cap, so one garbage feed tick booked a +43,137% (+$21,568 on a $50 position)
"gain", and ~197 winners booked above the +25% take-profit. These tests prove:
(a) a garbage price tick cannot book a gain, (b) a TP exit books at the threshold
price (never the raw tick), (c) balance == starting + sum(pnl) - open cost basis,
plus the state-file repair + reconcile-on-load hardening.
"""
import json
import math
import os
import tempfile
from datetime import datetime, timezone, timedelta

import core.paper_trading as pt

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)


def _pos(entry=0.002, opened_hours_ago=1):
    return {"entry_price": entry, "opened_at": (NOW - timedelta(hours=opened_hours_ago)).isoformat(),
            "qty": 50 / entry, "usd_in": 50, "symbol": "A/B",
            "pair_address": "0xp", "token_address": "0xt"}


class TestGarbageTickCannotBook:
    def test_the_real_glitch_holds_not_books(self):
        # the actual incident: entry 0.002, tick ~431x entry (+43,137%)
        assert pt.check_exit(_pos(0.002), 0.002 * 431.37, NOW, 25, 15, 24) is None

    def test_is_bad_tick_high_side_only(self):
        assert pt.is_bad_tick(0.002, 0.002 * 11, 10) is True     # 11x = glitch
        assert pt.is_bad_tick(0.002, 0.002 * 9, 10) is False     # 9x = allowed (books TP@thresh)
        assert pt.is_bad_tick(0.002, 0.0026, 10) is False        # +30% is not a glitch
        assert pt.is_bad_tick(1.0, 0.0001, 10) is False          # a crash is NOT a bad tick
        assert pt.is_bad_tick(0.002, None) is False              # defensive

    def test_bad_tick_does_not_trigger_a_spurious_exit(self):
        # a position mid-band gets one absurd tick -> must keep holding
        p = _pos(0.002)  # would be "at +5%" etc.; the glitch tick must not close it
        assert pt.check_exit(p, 0.002 * 5000, NOW, 25, 15, 24) is None


class TestThresholdBooking:
    def test_tp_books_at_threshold_not_observed_tick(self):
        reason, price = pt.check_exit(_pos(0.002), 0.0026, NOW, 25, 15, 24)  # observed +30%
        assert reason == "take-profit"
        assert math.isclose(price, 0.002 * 1.25, rel_tol=1e-9)              # booked +25%

    def test_big_but_sane_win_still_caps_at_tp(self):
        # 8x (+700%) is below the 10x glitch bar, so it books — but at +25%, not +700%
        st = pt.fresh_state()
        pos = pt.open_position(st, "0xp", "A/B", "0xt", 1.0, 80, NOW.isoformat(), 50)
        reason, price = pt.check_exit(pos, 8.0, NOW, 25, 15, 24)
        closed = pt.close_position(st, pos, price, reason, NOW.isoformat())
        assert closed["pnl_pct"] == 25.0
        assert math.isclose(closed["pnl_usd"], 12.5)  # not the +$350 the raw tick implied

    def test_sl_books_at_observed_price_not_threshold(self):
        # asymmetry: a dump fills below the stop, so SL books the real observed
        # price (-50%), NOT the -15% threshold
        reason, price = pt.check_exit(_pos(1.0), 0.5, NOW, 25, 15, 24)  # observed -50%
        assert reason == "stop-loss"
        assert math.isclose(price, 0.5, rel_tol=1e-9)

    def test_rug_books_near_full_loss_not_threshold(self):
        # an illiquid memecoin dumping to -95% must book ~-95%, not a flattering -15%
        st = pt.fresh_state()
        pos = pt.open_position(st, "0xp", "RUG/SOL", "0xt", 1.0, 80, NOW.isoformat(), 50)
        reason, price = pt.check_exit(pos, 0.05, NOW, 25, 15, 24)  # -95%
        closed = pt.close_position(st, pos, price, reason, NOW.isoformat())
        assert reason == "stop-loss"
        assert math.isclose(price, 0.05, rel_tol=1e-9)
        assert math.isclose(closed["pnl_pct"], -95.0)      # the real loss, not -15
        assert math.isclose(closed["pnl_usd"], -47.5)      # ~full loss on $50, not -7.5

    def test_time_stop_still_books_at_observed_sane_price(self):
        reason, price = pt.check_exit(_pos(1.0, opened_hours_ago=30), 1.02, NOW, 25, 15, 24)
        assert reason == "time-stop" and math.isclose(price, 1.02)


class TestBalanceReconciles:
    def test_identity_holds_after_a_sequence(self):
        st = pt.fresh_state()
        p1 = pt.open_position(st, "0xa", "A/B", "0xta", 0.002, 80, NOW.isoformat(), 50)
        r, px = pt.check_exit(p1, 0.0026, NOW, 25, 15, 24)          # +25% -> +12.5
        pt.close_position(st, p1, px, r, NOW.isoformat())
        p2 = pt.open_position(st, "0xb", "C/D", "0xtb", 1.0, 80, NOW.isoformat(), 50)
        r, px = pt.check_exit(p2, 0.5, NOW, 25, 15, 24)             # -50% observed -> -25
        pt.close_position(st, p2, px, r, NOW.isoformat())
        pt.open_position(st, "0xc", "E/F", "0xtc", 1.0, 80, NOW.isoformat(), 50)  # left open
        expected, drift = pt.reconcile_balance(st)
        assert abs(drift) < 1e-9
        # balance == starting + sum(pnl) - open cost basis
        assert math.isclose(st["balance_usd"], 1000 + (12.5 - 25.0) - 50)


def _corrupt_state():
    st = pt.fresh_state()
    st["closed"] = [
        {"symbol": "GLITCH/SOL", "usd_in": 50, "entry_price": 0.002, "exit_price": 0.863,
         "pnl_usd": 21568.52, "pnl_pct": 43137.0, "exit_reason": "take-profit"},
        {"symbol": "OVER/SOL", "usd_in": 50, "entry_price": 1.0, "exit_price": 1.6,
         "pnl_usd": 30.0, "pnl_pct": 60.0, "exit_reason": "take-profit"},
        {"symbol": "OK/SOL", "usd_in": 50, "entry_price": 1.0, "exit_price": 1.25,
         "pnl_usd": 12.5, "pnl_pct": 25.0, "exit_reason": "take-profit"},
        {"symbol": "LOSS/SOL", "usd_in": 50, "entry_price": 1.0, "exit_price": 0.85,
         "pnl_usd": -7.5, "pnl_pct": -15.0, "exit_reason": "stop-loss"},
    ]
    st["balance_usd"] = 1000 + 21568.52 + 30.0 + 12.5 - 7.5  # inflated to match the bug
    return st


class TestRepair:
    def test_caps_impossible_trades_and_keeps_audit_trail(self):
        st = _corrupt_state()
        rep = pt.repair_impossible_trades(st)
        assert rep["corrected"] == 2  # GLITCH (+43137%) and OVER (+60%)
        g = st["closed"][0]
        assert g["pnl_pct"] == 25.0 and math.isclose(g["pnl_usd"], 12.5)
        assert g["original_pnl_usd"] == 21568.52 and g["original_pnl_pct"] == 43137.0
        assert "corrected" in g
        # the honest trades are untouched
        assert st["closed"][2]["pnl_usd"] == 12.5 and "corrected" not in st["closed"][2]
        assert st["closed"][3]["pnl_usd"] == -7.5 and "corrected" not in st["closed"][3]

    def test_repair_is_idempotent(self):
        st = _corrupt_state()
        pt.repair_impossible_trades(st)
        assert pt.repair_impossible_trades(st)["corrected"] == 0

    def test_load_state_repairs_and_reconciles(self):
        st = _corrupt_state()
        d = tempfile.mkdtemp()
        p = os.path.join(d, "paper_state.json")
        json.dump(st, open(p, "w"))
        loaded = pt.load_state(p)
        # both impossible trades capped; balance reconciled to the trade-derived value
        _, drift = pt.reconcile_balance(loaded)
        assert abs(drift) < 1e-9
        # 1000 + (12.5 + 12.5 + 12.5 - 7.5) - 0 open = 1030.0
        assert math.isclose(loaded["balance_usd"], 1030.0)
        # all four records are still present (repair, not reset)
        assert len(loaded["closed"]) == 4
