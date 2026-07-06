# Offline unit tests for the portfolio-watch state machine (Part B, 2026-07-06).
# Pure functions only — no network, no env keys.

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from worker import watch_holdings, detect_portfolio_moves

NOW = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)


def _balances(cro=0.0, cro_usd=None, details=None, priced=True):
    return {"cro": cro, "cro_usd": cro_usd, "token_details": details or [], "priced": priced}


def test_watch_holdings_filters_and_includes_cro():
    b = _balances(
        cro=1000.0, cro_usd=81.0,
        details=[
            {"symbol": "XYO", "contract": "0xa", "amount": 100.0, "usd": 12.0},
            {"symbol": "DUST", "contract": "0xb", "amount": 5.0, "usd": 0.40},   # < $5 -> out
            {"symbol": "MOON", "contract": "0xc", "amount": 42.0, "usd": None},  # unpriced -> out
        ],
    )
    h = watch_holdings(b, min_usd=5.0)
    keys = {x["key"] for x in h}
    assert keys == {"native:CRO", "0xa"}
    cro = next(x for x in h if x["key"] == "native:CRO")
    assert abs(cro["price"] - 0.081) < 1e-12


def test_first_cycle_seeds_never_alerts():
    baseline, last_alert = {}, {}
    h = [{"key": "0xa", "symbol": "XYO", "amount": 100.0, "usd": 12.0, "price": 0.12}]
    moves = detect_portfolio_moves(h, baseline, last_alert, NOW, 10.0, 60.0)
    assert moves == []
    assert baseline["0xa"]["price"] == 0.12


def test_threshold_triggers_and_rebases():
    baseline = {"0xa": {"price": 0.10, "ts": "x"}}
    last_alert = {}
    h = [{"key": "0xa", "symbol": "XYO", "amount": 100.0, "usd": 12.0, "price": 0.12}]
    moves = detect_portfolio_moves(h, baseline, last_alert, NOW, 10.0, 60.0)
    assert len(moves) == 1
    mv = moves[0]
    assert abs(mv["move_pct"] - 20.0) < 1e-9
    assert mv["old_usd"] == 10.0 and mv["new_usd"] == 12.0
    assert baseline["0xa"]["price"] == 0.12  # rebased on alert


def test_small_drift_accumulates_until_threshold():
    baseline = {"0xa": {"price": 0.10, "ts": "x"}}
    # +6% -> no alert, baseline NOT rebased
    h = [{"key": "0xa", "symbol": "XYO", "amount": 100.0, "usd": 10.6, "price": 0.106}]
    assert detect_portfolio_moves(h, baseline, {}, NOW, 10.0, 60.0) == []
    assert baseline["0xa"]["price"] == 0.10
    # another +6% (cumulative +12.36%) -> alert
    h = [{"key": "0xa", "symbol": "XYO", "amount": 100.0, "usd": 11.24, "price": 0.11236}]
    moves = detect_portfolio_moves(h, baseline, {}, NOW, 10.0, 60.0)
    assert len(moves) == 1


def test_cooldown_suppresses_repeat_alerts():
    baseline = {"0xa": {"price": 0.10, "ts": "x"}}
    last_alert = {"0xa": NOW - timedelta(minutes=30)}  # alerted 30 min ago
    h = [{"key": "0xa", "symbol": "XYO", "amount": 100.0, "usd": 13.0, "price": 0.13}]
    assert detect_portfolio_moves(h, baseline, last_alert, NOW, 10.0, 60.0) == []
    # cooldown expired -> alert
    last_alert["0xa"] = NOW - timedelta(minutes=61)
    assert len(detect_portfolio_moves(h, baseline, last_alert, NOW, 10.0, 60.0)) == 1


def test_downward_moves_alert_too():
    baseline = {"0xa": {"price": 0.10, "ts": "x"}}
    h = [{"key": "0xa", "symbol": "XYO", "amount": 100.0, "usd": 8.5, "price": 0.085}]
    moves = detect_portfolio_moves(h, baseline, {}, NOW, 10.0, 60.0)
    assert len(moves) == 1 and moves[0]["move_pct"] < 0


def test_bad_baseline_price_reseeds_not_crashes():
    baseline = {"0xa": {"price": 0.0, "ts": "x"}}
    h = [{"key": "0xa", "symbol": "XYO", "amount": 100.0, "usd": 12.0, "price": 0.12}]
    assert detect_portfolio_moves(h, baseline, {}, NOW, 10.0, 60.0) == []
    assert baseline["0xa"]["price"] == 0.12


def test_crashed_holding_stays_watched_below_min_usd():
    # entered at $12, crashed to $0.60 (< $5 bar): must STAY watched and alert -95%
    baseline = {"0xa": {"price": 0.12, "ts": "x"}}
    b = _balances(details=[{"symbol": "XYO", "contract": "0xa", "amount": 100.0, "usd": 0.60}])
    h = watch_holdings(b, min_usd=5.0, baseline=baseline)
    assert len(h) == 1
    moves = detect_portfolio_moves(h, baseline, {}, NOW, 10.0, 60.0)
    assert len(moves) == 1 and moves[0]["move_pct"] < -90


def test_new_token_mid_run_seeds_without_alert():
    baseline = {"0xa": {"price": 0.12, "ts": "x"}}  # non-empty: not the first cycle
    h = [{"key": "0xb", "symbol": "NEW", "amount": 10.0, "usd": 50.0, "price": 5.0}]
    assert detect_portfolio_moves(h, baseline, {}, NOW, 10.0, 60.0) == []
    assert baseline["0xb"]["price"] == 5.0


def test_watch_holdings_never_raises_on_junk():
    assert watch_holdings({"cro": "junk", "token_details": "nope"}, 5.0) == []
