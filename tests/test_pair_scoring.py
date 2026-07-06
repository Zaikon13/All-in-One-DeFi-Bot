# Offline unit tests for worker.score_pair (Part A, 2026-07-05).
# Pure function, no network, no env keys needed (defaults apply).

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import worker
from worker import score_pair


def _pair(vol1h=0, buys=0, sells=0, chg1h=0):
    return {
        "volume": {"h1": vol1h},
        "txns": {"h1": {"buys": buys, "sells": sells}},
        "priceChange": {"h1": chg1h},
    }


def test_zero_pair_scores_only_liquidity():
    sc = score_pair(_pair(), liq=0.0)
    assert sc["score"] == 0.0


def test_perfect_pair_scores_100():
    sc = score_pair(_pair(vol1h=25000, buys=85, sells=15, chg1h=30), liq=50000)
    assert sc["score"] == 100.0
    assert sc["pts_volume"] == 25.0
    assert sc["pts_buys"] == 25.0
    assert sc["pts_momentum"] == 25.0
    assert sc["pts_liquidity"] == 25.0


def test_components_are_linear_and_capped():
    # half volume -> half points; overshoot -> capped at 25
    assert score_pair(_pair(vol1h=12500), liq=0)["pts_volume"] == 12.5
    assert score_pair(_pair(vol1h=10**9), liq=0)["pts_volume"] == 25.0
    # min-liquidity floor ($10k) on the $50k full scale -> 5 pts
    assert score_pair(_pair(), liq=10000)["pts_liquidity"] == 5.0


def test_buy_pressure_zero_at_or_below_50pct():
    assert score_pair(_pair(buys=10, sells=10), liq=0)["pts_buys"] == 0.0
    assert score_pair(_pair(buys=3, sells=7), liq=0)["pts_buys"] == 0.0
    # no transactions at all -> no buy-pressure points, no crash
    assert score_pair(_pair(), liq=0)["pts_buys"] == 0.0


def test_negative_momentum_gives_zero_not_negative():
    sc = score_pair(_pair(chg1h=-40), liq=0)
    assert sc["pts_momentum"] == 0.0
    assert sc["score"] >= 0.0


def test_non_finite_values_count_as_zero_not_bypass():
    # "nan"/"inf" parse as valid floats; they must yield 0 points, not score=nan
    # (nan < PAIR_MIN_SCORE is False and would sneak past the gate).
    sc = score_pair({"volume": {"h1": "nan"}, "priceChange": {"h1": "inf"}}, liq=float("inf"))
    assert sc["score"] == 0.0


def test_malformed_fields_never_raise():
    junk = {"volume": "nope", "txns": {"h1": {"buys": "x"}}, "priceChange": None}
    sc = score_pair(junk, liq=15000)
    assert 0.0 <= sc["score"] <= 100.0


def test_default_threshold_separates_dust_from_signal():
    # boring pair at the liquidity floor: only 5 pts -> below default bar (35)
    boring = score_pair(_pair(vol1h=500, buys=2, sells=2, chg1h=0.5), liq=10000)
    assert boring["score"] < worker.PAIR_MIN_SCORE
    # active pair: decent volume, buy-heavy, moving -> above the bar
    active = score_pair(_pair(vol1h=15000, buys=40, sells=12, chg1h=18), liq=30000)
    assert active["score"] >= worker.PAIR_MIN_SCORE
