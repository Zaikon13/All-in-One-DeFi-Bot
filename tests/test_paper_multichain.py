# Part 2 (2026-07-23) — offline tests for multi-chain paper: chain on positions,
# per-chain exit-price grouping, and pools/multi parsing. No network.

import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import paper_trading as pt
from core import pair_discovery as disc

NOW = datetime(2026, 7, 23, 20, 0, tzinfo=timezone.utc)


class TestChainOnPositions(unittest.TestCase):
    def test_open_records_chain_and_preserves_address_case(self):
        st = {"balance_usd": 1000.0, "starting_usd": 1000.0, "open": [], "closed": []}
        # a case-sensitive Solana-style address must NOT be lowercased
        pos = pt.open_position(st, "So1AnaPooLAddrCASE", "MOON/SOL", "TokAddr", 5.0, 72,
                               NOW.isoformat(), position_usd=50, chain="solana")
        self.assertEqual(pos["chain"], "solana")
        self.assertEqual(pos["pair_address"], "So1AnaPooLAddrCASE")

    def test_default_chain_is_cro(self):
        st = {"balance_usd": 1000.0, "starting_usd": 1000.0, "open": [], "closed": []}
        pos = pt.open_position(st, "0xabc", "A/B", "0xt", 1.0, 71, NOW.isoformat())
        self.assertEqual(pos["chain"], "cro")


class TestGroupByChain(unittest.TestCase):
    def test_groups_and_defaults_missing_chain(self):
        opens = [
            {"chain": "solana", "pair_address": "S1"},
            {"chain": "cro", "pair_address": "0x1"},
            {"pair_address": "0x2"},  # legacy, no chain -> cro
            {"chain": "sui-network", "pair_address": "0xsui"},
        ]
        g = pt.group_open_by_chain(opens)
        self.assertEqual(set(g.keys()), {"solana", "cro", "sui-network"})
        self.assertEqual(len(g["cro"]), 2)  # 0x1 + legacy 0x2

    def test_empty(self):
        self.assertEqual(pt.group_open_by_chain([]), {})


class TestParsePoolPrices(unittest.TestCase):
    def test_keys_both_cases_skips_bad(self):
        body = {"data": [
            {"attributes": {"address": "So1CASE", "base_token_price_usd": "2.5"}},
            {"attributes": {"address": "0xABC", "base_token_price_usd": "0.001"}},
            {"attributes": {"address": "0xdead", "base_token_price_usd": "0"}},   # <=0 skip
            {"attributes": {"address": "0xbad", "base_token_price_usd": "nope"}}, # unparseable skip
            {"attributes": {"address": "", "base_token_price_usd": "1"}},         # no addr skip
        ]}
        p = disc.parse_pool_prices(body)
        self.assertEqual(p["So1CASE"], 2.5)
        self.assertEqual(p["so1case"], 2.5)      # lowercased alias
        self.assertEqual(p["0xABC"], 0.001)
        self.assertNotIn("0xdead", p)
        self.assertNotIn("0xbad", p)

    def test_empty_body_safe(self):
        self.assertEqual(disc.parse_pool_prices({}), {})
        self.assertEqual(disc.parse_pool_prices(None), {})


class TestExitPricingMatch(unittest.TestCase):
    """A position priced from pools/multi must match by pool address regardless of case."""
    def test_solana_case_sensitive_match(self):
        st = {"balance_usd": 950.0, "starting_usd": 1000.0, "open": [], "closed": []}
        pos = pt.open_position(st, "So1AnaPooLAddrCASE", "MOON/SOL", "tok", 5.0, 72,
                               NOW.isoformat(), position_usd=50, chain="solana")
        # +25% -> take-profit at 6.25
        prices = disc.parse_pool_prices({"data": [
            {"attributes": {"address": "So1AnaPooLAddrCASE", "base_token_price_usd": "6.25"}}]})
        cp = prices.get(pos["pair_address"]) or prices.get(pos["pair_address"].lower())
        res = pt.check_exit(pos, cp, NOW, 25, 15, 24)
        self.assertEqual(res[0], "take-profit")


if __name__ == "__main__":
    unittest.main()
