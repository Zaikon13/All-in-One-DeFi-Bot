# Part 1 (2026-07-24) — Solana maturity via direct pools/multi force-fetch.
# A pending pool that NEVER reappears in new_pools must still mature via the
# direct fetch. Offline — no network.

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import worker
from core import pair_discovery as disc

NOW = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)


class TestPendingDueKeys(unittest.TestCase):
    def _pending(self):
        return {
            # solana pool first seen at age ~0, now 25 min old -> DUE (matured age)
            "solana:sopool1": {"ca": (NOW - timedelta(minutes=25)).isoformat(), "addr": "SoPoOL1CaSe"},
            # solana still too young (5 min) -> not due
            "solana:sopool2": {"ca": (NOW - timedelta(minutes=5)).isoformat(), "addr": "SoPoOL2"},
            # solana expired (older than 24h) -> not due
            "solana:sopool3": {"ca": (NOW - timedelta(hours=30)).isoformat(), "addr": "SoPoOL3"},
            # cro pool due, but different chain
            "cro:0xabc": {"ca": (NOW - timedelta(hours=1)).isoformat(), "addr": "0xABC"},
        }

    def test_only_matured_this_chain_are_due(self):
        due = worker.pending_due_keys(self._pending(), "solana", NOW, 20, 24)
        self.assertEqual(due, ["solana:sopool1"])

    def test_cro_scoped_separately(self):
        due = worker.pending_due_keys(self._pending(), "cro", NOW, 20, 24)
        self.assertEqual(due, ["cro:0xabc"])

    def test_legacy_string_value_supported(self):
        pending = {"solana:x": (NOW - timedelta(minutes=25)).isoformat()}  # legacy str
        self.assertEqual(worker.pending_due_keys(pending, "solana", NOW, 20, 24), ["solana:x"])

    def test_original_address_preserved_for_fetch(self):
        # the DUE key maps to the ORIGINAL-case address (Solana base58 sensitive)
        pending = self._pending()
        due = worker.pending_due_keys(pending, "solana", NOW, 20, 24)
        self.assertEqual(pending[due[0]]["addr"], "SoPoOL1CaSe")


class TestForceFetchMatures(unittest.TestCase):
    """The direct pools/multi fetch turns pending addresses into scoreable pools
    even though they never reappeared in new_pools."""
    def test_fetch_pools_by_address_parses(self):
        import asyncio

        class _Resp:
            status_code = 200
            def json(self):
                return {"data": [{"attributes": {"address": "SoPoOL1CaSe", "name": "MOON / SOL",
                                                 "reserve_in_usd": "25000", "base_token_price_usd": "0.5",
                                                 "volume_usd": {"h1": "8000"},
                                                 "price_change_percentage": {"h1": "12"},
                                                 "transactions": {"h1": {"buys": 40, "sells": 12}}},
                                  "relationships": {"base_token": {"data": {"id": "solana_MooNMint"}},
                                                    "quote_token": {"data": {"id": "solana_SoLMint"}},
                                                    "dex": {"data": {"id": "raydium"}}}}]}

        class _Client:
            async def get(self, url, params=None, headers=None, timeout=None):
                assert "pools/multi/SoPoOL1CaSe" in url  # original case preserved in request
                return _Resp()

        norms = asyncio.get_event_loop().run_until_complete(
            disc.fetch_pools_by_address(_Client(), "solana", ["SoPoOL1CaSe"]))
        self.assertEqual(len(norms), 1)
        n = norms[0]
        self.assertEqual(n["key"], "solana:sopool1case")
        self.assertEqual(n["baseToken"]["symbol"], "MOON")
        self.assertEqual(n["liquidity_usd"], 25000.0)
        self.assertEqual(n["volume"]["h1"], 8000.0)          # scoreable now
        self.assertEqual(n["txns"]["h1"], {"buys": 40, "sells": 12})


if __name__ == "__main__":
    unittest.main()
