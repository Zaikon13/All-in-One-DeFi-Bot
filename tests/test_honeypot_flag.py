"""Part 3 (2026-07-24) — honeypot / zero-sell flag.

The scorer rewards a high buy ratio as max buy-pressure, so a pool that can be
bought but never sold (0 sells, many buys) LOOKS great and would score high.
`is_honeypot_suspect` is a pure, informational flag surfaced in alerts, /signals,
and recorded on paper positions. It does NOT alter the scoring math and does not
block paper entry by default (HONEYPOT_BLOCK_PAPER_ENTRY=false — we want the
evidence). These offline tests pin the logic and the paper-position recording.
"""
import core.pair_discovery as disc
import core.paper_trading as paper


class TestHoneypotFlag:
    def test_zero_sells_many_buys_is_suspect(self):
        assert disc.is_honeypot_suspect(buys=5, sells=0) is True
        assert disc.is_honeypot_suspect(buys=50, sells=0) is True

    def test_below_min_buys_not_suspect(self):
        # default HONEYPOT_MIN_BUYS = 5; four buys is not enough signal
        assert disc.is_honeypot_suspect(buys=4, sells=0) is False

    def test_any_sells_not_suspect(self):
        # even a single sell proves the token is sellable
        assert disc.is_honeypot_suspect(buys=100, sells=1) is False

    def test_dead_pool_not_suspect(self):
        # 0 buys AND 0 sells is just an inactive pool, not a honeypot
        assert disc.is_honeypot_suspect(buys=0, sells=0) is False

    def test_custom_min_buys(self):
        assert disc.is_honeypot_suspect(buys=3, sells=0, min_buys=3) is True
        assert disc.is_honeypot_suspect(buys=2, sells=0, min_buys=3) is False

    def test_bad_input_is_safe(self):
        assert disc.is_honeypot_suspect(buys=None, sells=None) is False
        assert disc.is_honeypot_suspect(buys="x", sells="y") is False

    def test_scoring_math_unchanged(self):
        # A max-buy-pressure, zero-sell pool still scores exactly as before —
        # the flag is additive, never subtractive. score_pair reads the
        # Dexscreener-shaped dict the worker maps GeckoTerminal fields into.
        import worker
        sc = worker.score_pair({"volume": {"h1": 25000},
                                "txns": {"h1": {"buys": 40, "sells": 0}},
                                "priceChange": {"h1": 30.0}}, 50000)
        assert sc["buys"] == 40 and sc["sells"] == 0
        assert sc["score"] == 100  # full marks; the honeypot flag does not deduct
        assert worker.disc.is_honeypot_suspect(sc["buys"], sc["sells"]) is True


class TestPaperRecordsFlag:
    def test_open_position_records_suspicious(self):
        state = paper.fresh_state()
        pos = paper.open_position(state, "0xpool", "MOON/WCRO", "0xtok",
                                  price=0.01, score=80.0, now_iso="2026-07-24T00:00:00+00:00",
                                  flags={"suspicious": True})
        assert pos["flags"]["suspicious"] is True

    def test_open_position_default_no_flags(self):
        state = paper.fresh_state()
        pos = paper.open_position(state, "0xpool", "SAFE/WCRO", "0xtok",
                                  price=0.01, score=80.0, now_iso="2026-07-24T00:00:00+00:00")
        assert pos["flags"] == {}
