# Multi-chain discovery (2026-07-23) — offline tests for GeckoTerminal parsing,
# the maturity rule, per-chain config, and the per-chain funnel/digest. No network.

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import pair_discovery as disc

NOW = datetime(2026, 7, 23, 20, 0, tzinfo=timezone.utc)


def _pool(addr="0xabc", created="2026-07-23T18:00:00Z", liq="16492.0",
          vol1h="1234.5", pc1h="12.3", buys=32, sells=39, price="0.0012",
          base_id="cro_0xtoken", quote_id="cro_0xwcro", dex="vvs-finance", name="WOOF / WCRO"):
    return {
        "attributes": {"address": addr, "pool_created_at": created,
                       "reserve_in_usd": liq, "name": name, "base_token_price_usd": price,
                       "fdv_usd": "50000",
                       "volume_usd": {"h1": vol1h}, "price_change_percentage": {"h1": pc1h},
                       "transactions": {"h1": {"buys": buys, "sells": sells}}},
        "relationships": {"base_token": {"data": {"id": base_id}},
                          "quote_token": {"data": {"id": quote_id}},
                          "dex": {"data": {"id": dex}}},
    }


INCLUDED = {"cro_0xtoken": {"id": "cro_0xtoken", "attributes": {"symbol": "WOOF", "address": "0xtoken"}},
            "cro_0xwcro": {"id": "cro_0xwcro", "attributes": {"symbol": "WCRO", "address": "0xwcro"}}}


class TestParse(unittest.TestCase):
    def test_maps_geckoterminal_into_score_shape(self):
        n = disc.parse_gt_pool(_pool(), "cro", INCLUDED)
        self.assertEqual(n["key"], "cro:0xabc")
        self.assertEqual(n["chain"], "cro")
        self.assertEqual(n["dex"], "vvs-finance")
        self.assertEqual(n["baseToken"], {"symbol": "WOOF", "address": "0xtoken"})
        self.assertEqual(n["quoteToken"]["symbol"], "WCRO")
        self.assertEqual(n["liquidity_usd"], 16492.0)
        self.assertEqual(n["priceUsd"], "0.0012")
        self.assertEqual(n["volume"]["h1"], 1234.5)
        self.assertEqual(n["txns"]["h1"], {"buys": 32, "sells": 39})
        self.assertEqual(n["priceChange"]["h1"], 12.3)
        self.assertIn("geckoterminal.com/cro/pools/0xabc", n["url"])

    def test_symbol_falls_back_to_name_when_not_included(self):
        n = disc.parse_gt_pool(_pool(base_id="sui-network_0xdeadbeef", quote_id="sui-network_0xsui",
                                     name="SPX / SUI"), "sui-network", {})
        self.assertEqual(n["baseToken"]["symbol"], "SPX")
        self.assertEqual(n["baseToken"]["address"], "0xdeadbeef")
        self.assertEqual(n["quoteToken"]["symbol"], "SUI")

    def test_missing_address_returns_none(self):
        p = _pool(); p["attributes"]["address"] = ""
        self.assertIsNone(disc.parse_gt_pool(p, "cro", {}))

    def test_junk_fields_never_raise_and_zero_out(self):
        p = {"attributes": {"address": "0x1", "reserve_in_usd": "nope",
                            "volume_usd": "bad", "transactions": None,
                            "price_change_percentage": {"h1": "x"}}}
        n = disc.parse_gt_pool(p, "solana", {})
        self.assertEqual(n["liquidity_usd"], 0.0)
        self.assertEqual(n["volume"]["h1"], 0.0)
        self.assertEqual(n["txns"]["h1"], {"buys": 0, "sells": 0})
        self.assertEqual(n["priceChange"]["h1"], 0.0)


class TestClassify(unittest.TestCase):
    def test_too_young_is_pending(self):
        self.assertEqual(disc.classify_pool((NOW - timedelta(minutes=5)).isoformat(), NOW, 20, 24), "pending")

    def test_matured_in_window(self):
        self.assertEqual(disc.classify_pool((NOW - timedelta(hours=2)).isoformat(), NOW, 20, 24), "mature")

    def test_boundary_at_min_age(self):
        self.assertEqual(disc.classify_pool((NOW - timedelta(minutes=20)).isoformat(), NOW, 20, 24), "mature")

    def test_expired_past_window(self):
        self.assertEqual(disc.classify_pool((NOW - timedelta(hours=30)).isoformat(), NOW, 20, 24), "expired")

    def test_unparseable_is_unknown_never_scored(self):
        self.assertEqual(disc.classify_pool(None, NOW, 20, 24), "unknown")
        self.assertEqual(disc.classify_pool("garbage", NOW, 20, 24), "unknown")

    def test_future_pool_held_pending_not_scored(self):
        self.assertEqual(disc.classify_pool((NOW + timedelta(minutes=10)).isoformat(), NOW, 20, 24), "pending")


class TestConfig(unittest.TestCase):
    def test_defaults(self):
        for k in ("PAIR_MIN_LIQUIDITY_USD_CRO", "PAIR_MIN_LIQUIDITY_USD_SOLANA",
                  "PAIR_MIN_LIQUIDITY_USD_SUI_NETWORK", "CHAINS_ENABLED"):
            os.environ.pop(k, None)
        self.assertEqual(disc.chains_enabled(), ["cro", "solana", "sui-network"])
        self.assertEqual(disc.min_liquidity_for("cro"), 5000.0)
        self.assertEqual(disc.min_liquidity_for("solana"), 10000.0)
        self.assertEqual(disc.min_liquidity_for("sui-network"), 10000.0)
        self.assertEqual(disc.min_score_for("solana", 35.0), 35.0)

    def test_env_override_per_chain(self):
        os.environ["PAIR_MIN_LIQUIDITY_USD_CRO"] = "1000"
        os.environ["PAIR_MIN_SCORE_SOLANA"] = "60"
        os.environ["CHAINS_ENABLED"] = "solana, cro"
        try:
            self.assertEqual(disc.min_liquidity_for("cro"), 1000.0)
            self.assertEqual(disc.min_score_for("solana", 35.0), 60.0)
            self.assertEqual(disc.chains_enabled(), ["solana", "cro"])
        finally:
            for k in ("PAIR_MIN_LIQUIDITY_USD_CRO", "PAIR_MIN_SCORE_SOLANA", "CHAINS_ENABLED"):
                os.environ.pop(k, None)


class TestChainFunnel(unittest.TestCase):
    def test_record_and_format_multichain(self):
        import worker
        st = {}
        worker.record_chain_funnel(st, "cro", seen=5, matured=3, passed=0, sent=0)
        worker.record_chain_funnel(st, "solana", seen=20, matured=14, passed=2, sent=2, best=(71, "MOON"))
        worker.record_chain_funnel(st, "sui-network", seen=20, matured=18, passed=1, sent=1, best=(58, "SPX"))
        msg = worker.format_multichain_digest(st, ["cro", "solana", "sui-network"])
        self.assertIn("cro: seen 5, matured 3, passed 0", msg)
        self.assertIn("solana: seen 20, matured 14, passed 2, best 71 (MOON)", msg)
        self.assertIn("sui: seen 20, matured 18, passed 1, best 58 (SPX)", msg)
        self.assertIn("· sent 3", msg)
        self.assertNotIn("\n", msg)

    def test_best_tracks_max_and_symbol_sanitized(self):
        import worker
        st = {}
        worker.record_chain_funnel(st, "solana", best=(40, "A_B*C"))
        worker.record_chain_funnel(st, "solana", best=(70, "WIN"))
        worker.record_chain_funnel(st, "solana", best=(10, "LOW"))
        self.assertEqual(st["solana"]["best_score"], 70.0)
        self.assertEqual(st["solana"]["best_symbol"], "WIN")
        worker.record_chain_funnel(st, "cro", best=(90, "X_Y*Z"))
        self.assertEqual(st["cro"]["best_symbol"], "XYZ")


if __name__ == "__main__":
    unittest.main()
