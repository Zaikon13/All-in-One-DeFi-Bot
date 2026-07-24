"""Part 4 (2026-07-24) — fake-liquidity sanity flag.

A pool can report enormous `reserve_in_usd` while almost nothing trades through
it. That inflated-liquidity signature earns full liquidity points in the scorer
and would poison paper-trading evidence if entered. `is_implausible_liquidity` is
a pure flag (huge reserve AND near-zero 1h volume). Unlike the honeypot flag, it
DOES gate paper entry by default (LIQ_SANITY_BLOCK_PAPER_ENTRY=true). It does NOT
change the scoring math. These offline tests pin the logic and paper recording.
"""
import core.pair_discovery as disc
import core.paper_trading as paper


class TestFakeLiquidityFlag:
    def test_huge_reserve_no_volume_is_implausible(self):
        assert disc.is_implausible_liquidity(reserve_usd=2_000_000, vol1h=500) is True

    def test_huge_reserve_with_real_volume_is_fine(self):
        # a genuinely deep pool sees genuine flow
        assert disc.is_implausible_liquidity(reserve_usd=2_000_000, vol1h=50_000) is False

    def test_small_pool_never_implausible(self):
        # below the reserve ceiling — not our concern regardless of volume
        assert disc.is_implausible_liquidity(reserve_usd=50_000, vol1h=0) is False

    def test_boundary_reserve_must_exceed_max(self):
        # exactly at the ceiling is not "> max"; needs to exceed it
        assert disc.is_implausible_liquidity(reserve_usd=1_000_000, vol1h=0) is False
        assert disc.is_implausible_liquidity(reserve_usd=1_000_000.01, vol1h=0) is True

    def test_boundary_volume_must_be_below_min(self):
        assert disc.is_implausible_liquidity(reserve_usd=2_000_000, vol1h=10_000) is False
        assert disc.is_implausible_liquidity(reserve_usd=2_000_000, vol1h=9_999) is True

    def test_custom_thresholds(self):
        assert disc.is_implausible_liquidity(600_000, 100, max_usd=500_000, min_vol=1_000) is True
        assert disc.is_implausible_liquidity(400_000, 100, max_usd=500_000, min_vol=1_000) is False

    def test_bad_and_nonfinite_input_is_safe(self):
        assert disc.is_implausible_liquidity(reserve_usd=None, vol1h=None) is False
        assert disc.is_implausible_liquidity(reserve_usd="x", vol1h="y") is False
        assert disc.is_implausible_liquidity(reserve_usd=float("inf"), vol1h=0) is False
        assert disc.is_implausible_liquidity(reserve_usd=float("nan"), vol1h=0) is False

    def test_scoring_math_unchanged(self):
        # An inflated-reserve pool still earns full liquidity points — the flag is
        # additive, never subtractive.
        import worker
        sc = worker.score_pair({"volume": {"h1": 500},
                                "txns": {"h1": {"buys": 1, "sells": 1}},
                                "priceChange": {"h1": 0.0}}, 2_000_000)
        assert sc["pts_liquidity"] == 25.0  # full liquidity marks
        assert worker.disc.is_implausible_liquidity(2_000_000, sc["vol1h"]) is True


class TestPaperRecordsFlag:
    def test_open_position_records_implausible(self):
        state = paper.fresh_state()
        pos = paper.open_position(state, "0xpool", "FAKE/WCRO", "0xtok",
                                  price=0.01, score=80.0, now_iso="2026-07-24T00:00:00+00:00",
                                  flags={"suspicious": False, "implausible_liq": True})
        assert pos["flags"]["implausible_liq"] is True
        assert pos["flags"]["suspicious"] is False
