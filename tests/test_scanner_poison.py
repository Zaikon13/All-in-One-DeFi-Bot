# Round-2 SC1 (2026-11-04): one malformed GeckoTerminal pool must never abort
# the scanner. parse_gt_pool is total (inf/nan counts, numeric symbols/names,
# list-valued ids), each fetcher skips a bad pool on its own, and the next chain
# is still fetched in the same cycle. Offline: fake clients / httpx.MockTransport.

import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import pair_discovery as disc


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _pool(addr="GoodPool1", **attrs_over):
    attrs = {"address": addr, "name": "MOON / SOL", "reserve_in_usd": "25000",
             "base_token_price_usd": "0.5", "volume_usd": {"h1": "8000"},
             "price_change_percentage": {"h1": "12"},
             "transactions": {"h1": {"buys": 40, "sells": 12}}}
    attrs.update(attrs_over)
    return {"attributes": attrs,
            "relationships": {"base_token": {"data": {"id": "solana_MooNMint"}},
                              "quote_token": {"data": {"id": "solana_SoLMint"}},
                              "dex": {"data": {"id": "raydium"}}}}


class TestParseGtPoolIsTotal(unittest.TestCase):
    def test_inf_buys_nan_sells_give_zero(self):
        p = _pool(transactions={"h1": {"buys": float("inf"), "sells": float("nan")}})
        n = disc.parse_gt_pool(p, "solana", {})
        self.assertIsInstance(n, dict)
        self.assertEqual(n["txns"]["h1"], {"buys": 0, "sells": 0})

    def test_numeric_symbol_is_stringified(self):
        inc = {"solana_MooNMint": {"id": "solana_MooNMint",
                                   "attributes": {"address": "MooNMint", "symbol": 420}}}
        n = disc.parse_gt_pool(_pool(), "solana", inc)
        self.assertEqual(n["baseToken"]["symbol"], "420")

    def test_numeric_name_does_not_raise(self):
        n = disc.parse_gt_pool(_pool(name=123), "solana", {})
        self.assertIsInstance(n, dict)

    def test_list_valued_base_token_id_does_not_raise(self):
        p = _pool()
        p["relationships"]["base_token"]["data"]["id"] = ["solana_x"]
        inc = {"solana_MooNMint": {"id": "solana_MooNMint", "attributes": {"symbol": "MOON"}}}
        n = disc.parse_gt_pool(p, "solana", inc)  # must not raise (unhashable id)
        self.assertIsInstance(n, dict)


class _Resp:
    def __init__(self, body):
        self.status_code = 200
        self._body = body

    def json(self):
        return self._body


class _Client:
    """Fake client in the shape of tests/test_solana_maturity.py's _Client."""

    def __init__(self, body):
        self.body = body
        self.calls = 0

    async def get(self, url, params=None, headers=None, timeout=None):
        self.calls += 1
        return _Resp(self.body)


class TestFetchPoolsByAddressSkipsPoison(unittest.TestCase):
    def test_poison_then_good_returns_both_without_raising(self):
        poison = _pool("PoisonPool", transactions={"h1": {"buys": float("inf")}})
        inc = [{"id": "solana_MooNMint", "attributes": {"address": "MooNMint", "symbol": 5}}]
        body = {"data": [poison, _pool("GoodPool1")], "included": inc}
        out = _run(disc.fetch_pools_by_address(_Client(body), "solana",
                                               ["PoisonPool", "GoodPool1"]))
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["txns"]["h1"]["buys"], 0)
        self.assertEqual(out[0]["baseToken"]["symbol"], "5")

    def test_list_body_returns_empty(self):
        out = _run(disc.fetch_pools_by_address(_Client([1, 2, 3]), "solana", ["GoodPool1"]))
        self.assertEqual(out, [])


class TestFetchNewPoolsSkipsPoison(unittest.TestCase):
    def setUp(self):
        for p in (mock.patch.object(disc.asyncio, "sleep", new=mock.AsyncMock()),
                  mock.patch.dict(disc.LAST_FETCH_STATUS, {}, clear=True)):
            p.start()
            self.addCleanup(p.stop)

    def test_dict_address_pool_is_skipped_page_kept(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={"data": [_pool({"nested": "x"}), _pool("GoodPool1")]})

        async def go():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                return await disc.fetch_new_pools(client, "solana")

        out = _run(go())
        self.assertEqual([n["pairAddress"] for n in out], ["GoodPool1"])
        self.assertTrue(disc.LAST_FETCH_STATUS["solana"]["ok"])
        self.assertEqual(len(requests), 1)


class _StopLoop(BaseException):
    """Sentinel from the patched sleep; BaseException so no `except Exception` eats it."""


_RealAsyncClient = httpx.AsyncClient


class TestScannerSurvivesPoisonPendingPool(unittest.TestCase):
    """One real poll_new_pools cycle: a due Solana pending pool whose pools/multi
    row is poison (buys=Infinity, numeric name) must not stop Sui being fetched
    and alerted in the same cycle."""

    def test_next_chain_still_fetched_and_alerted(self):
        import worker
        from core import paper_trading as paper

        now = datetime.now(timezone.utc)
        sui_pool = {"id": "sui-network_0xsuipool", "type": "pool",
                    "attributes": {"address": "0xSuiPool", "name": "SPX / SUI",
                                   "base_token_price_usd": "0.1", "reserve_in_usd": "50000",
                                   "pool_created_at": (now - timedelta(hours=2)).isoformat(),
                                   "volume_usd": {"h1": "30000"},
                                   "price_change_percentage": {"h1": "40"},
                                   "transactions": {"h1": {"buys": 90, "sells": 10}}},
                    "relationships": {"base_token": {"data": {"id": "sui-network_0xspx"}},
                                      "quote_token": {"data": {"id": "sui-network_0xsui"}},
                                      "dex": {"data": {"id": "cetus"}}}}
        poison_raw = (b'{"data":[{"attributes":{"address":"PoisonPool","name":7,'
                      b'"transactions":{"h1":{"buys":Infinity}}}}]}')
        requested = []

        def handler(request):
            url = str(request.url)
            requested.append(url)
            if "/networks/solana/new_pools" in url:
                return httpx.Response(200, json={"data": []})
            if "/networks/solana/pools/multi/" in url:
                return httpx.Response(200, content=poison_raw,
                                      headers={"content-type": "application/json"})
            if "/networks/sui-network/new_pools" in url:
                return httpx.Response(200, json={"data": [sui_pool]})
            raise httpx.ConnectError(f"offline test: unexpected request to {url}")

        def client_factory(**kw):
            kw.pop("transport", None)
            return _RealAsyncClient(transport=httpx.MockTransport(handler), **kw)

        sent = []

        async def rec(text):
            sent.append(text)

        pending = {"solana:poisonpool": {"ca": (now - timedelta(hours=1)).isoformat(),
                                         "addr": "PoisonPool"}}
        patches = [
            mock.patch.object(worker, "chains_enabled", lambda: ["solana", "sui-network"]),
            mock.patch.object(worker, "pending_pools", pending),
            mock.patch.object(worker, "seen_pairs", set()),
            mock.patch.object(worker, "pair_last_seen", {}),
            mock.patch.object(worker, "recent_signals", []),
            mock.patch.object(worker, "signals_state", {}),
            mock.patch.object(worker, "chain_stats", {}),
            mock.patch.object(worker, "save_known_pairs", new=mock.MagicMock()),
            mock.patch.object(worker, "save_pending_pools", new=mock.MagicMock()),
            mock.patch.object(worker, "send_telegram", new=rec),
            mock.patch.object(worker, "PAIR_MIN_SCORE", 35.0),
            mock.patch.object(worker, "PAIR_MIN_AGE_MINUTES", 20.0),
            mock.patch.object(worker, "PAIR_NEWNESS_WINDOW_HOURS", 24.0),
            mock.patch.object(paper, "PAPER_TRADING_ENABLED", False),
            mock.patch.object(worker.httpx, "AsyncClient", client_factory),
            mock.patch.object(worker.asyncio, "sleep", new=mock.AsyncMock(side_effect=_StopLoop())),
            mock.patch.dict(disc.LAST_FETCH_STATUS, {}, clear=True),
            mock.patch.dict(os.environ, {"PAIR_MIN_LIQUIDITY_USD_SUI_NETWORK": "",
                                         "PAIR_MIN_SCORE_SUI_NETWORK": "",
                                         "PAIR_MIN_LIQUIDITY_USD_SOLANA": "",
                                         "PAIR_MIN_SCORE_SOLANA": ""}),
        ]
        for p in patches:
            p.start()
        try:
            with self.assertRaises(_StopLoop):
                _run(worker.poll_new_pools())
        finally:
            for p in reversed(patches):
                p.stop()

        self.assertTrue(any("/networks/solana/pools/multi/PoisonPool" in u for u in requested), requested)
        self.assertTrue(any("/networks/sui-network/new_pools" in u for u in requested), requested)
        alerts = [m for m in sent if "New Pool Detected" in m]
        self.assertEqual(len(alerts), 1, sent)


if __name__ == "__main__":
    unittest.main()
