# Critical-function tests (docs/CRITICAL_FUNCTIONS.md, Tier 3):
#   core/pair_discovery.py `fetch_new_pools`, `fetch_pool_prices` — all pool data.
#   Invariant: 429 backoff; never raises; fetch status recorded.
# Offline: a real httpx.AsyncClient over httpx.MockTransport; asyncio.sleep is an
# AsyncMock (the backoff is asserted, never actually slept).

import asyncio
import os
import sys
import unittest
from datetime import datetime
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


def _gt_pool(addr, price="0.5"):
    return {"id": f"cro_{addr}", "type": "pool",
            "attributes": {"address": addr, "name": "WOOF / WCRO", "base_token_price_usd": price,
                           "reserve_in_usd": "25000", "pool_created_at": "2026-11-04T10:00:00Z",
                           "volume_usd": {"h1": "5000"}, "price_change_percentage": {"h1": "12"},
                           "transactions": {"h1": {"buys": 10, "sells": 4}}},
            "relationships": {"base_token": {"data": {"id": "cro_0xbase"}},
                              "quote_token": {"data": {"id": "cro_0xquote"}},
                              "dex": {"data": {"id": "vvs"}}}}


def _new_pools_body(*addrs):
    return {"data": [_gt_pool(a) for a in addrs],
            "included": [{"id": "cro_0xbase", "attributes": {"address": "0xbase", "symbol": "WOOF"}}]}


class _Feed:
    """MockTransport handler driven by a script of responses (or exceptions)."""

    def __init__(self, *script):
        self.script = list(script)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(step, Exception):
            raise step
        if callable(step):
            return step(request)
        status, body = step
        if isinstance(body, (dict, list)):
            return httpx.Response(status, json=body)
        return httpx.Response(status, text=body or "")


async def _with_client(feed, fn):
    async with httpx.AsyncClient(transport=httpx.MockTransport(feed)) as client:
        return await fn(client)


class _Isolated(unittest.TestCase):
    def setUp(self):
        self.sleep = mock.AsyncMock()
        for p in (mock.patch.object(disc.asyncio, "sleep", new=self.sleep),
                  mock.patch.dict(disc.LAST_FETCH_STATUS, {}, clear=True)):
            p.start()
            self.addCleanup(p.stop)

    def slept(self):
        return [c.args[0] for c in self.sleep.await_args_list]


class TestFetchNewPools(_Isolated):
    def test_429_backs_off_then_succeeds_and_records_ok(self):
        """Invariant: 429 backoff + fetch status recorded. Two 429s back off 1s, 2s,
        then the 200 is parsed and recorded ok. Mutation that breaks it: dropping
        the `await asyncio.sleep(...)` on 429 (hammers a 30-calls/min API)."""
        feed = _Feed((429, {}), (429, {}), (200, _new_pools_body("0xPOOL1")))
        pools = _run(_with_client(feed, lambda c: disc.fetch_new_pools(c, "cro")))
        self.assertEqual([p["key"] for p in pools], ["cro:0xpool1"])
        self.assertEqual(self.slept(), [1.0, 2.0])
        self.assertEqual(len(feed.requests), 3)
        self.assertTrue(disc.LAST_FETCH_STATUS["cro"]["ok"])
        datetime.fromisoformat(disc.LAST_FETCH_STATUS["cro"]["ts"])   # a real timestamp

    def test_persistent_429_gives_up_empty_and_records_failure(self):
        """Invariant: 429 backoff (exponential, bounded) + never raises + status
        recorded as failed, so /signals says 'feed unavailable', not 'seen 0'."""
        feed = _Feed((429, {}))
        pools = _run(_with_client(feed, lambda c: disc.fetch_new_pools(c, "cro", max_retries=3)))
        self.assertEqual(pools, [])
        self.assertEqual(self.slept(), [1.0, 2.0, 4.0])
        self.assertEqual(len(feed.requests), 4)
        self.assertFalse(disc.LAST_FETCH_STATUS["cro"]["ok"])

    def test_http_error_records_failure_over_a_previous_success(self):
        """Invariant: fetch status recorded — a 5xx flips a previous ok=True to
        ok=False (a stale 'ok' would hide the outage). Never raises."""
        disc.LAST_FETCH_STATUS["cro"] = {"ok": True, "ts": "2026-11-04T00:00:00+00:00"}
        pools = _run(_with_client(_Feed((503, "unavailable")), lambda c: disc.fetch_new_pools(c, "cro")))
        self.assertEqual(pools, [])
        self.assertFalse(disc.LAST_FETCH_STATUS["cro"]["ok"])

    def test_transport_exception_never_raises(self):
        """Invariant: never raises — a connection error on every attempt backs off,
        returns [] and records the failure."""
        feed = _Feed(httpx.ConnectError("dns down"))
        pools = _run(_with_client(feed, lambda c: disc.fetch_new_pools(c, "solana")))
        self.assertEqual(pools, [])
        self.assertEqual(len(feed.requests), 4)
        self.assertEqual(self.slept(), [1.0, 2.0, 4.0])
        self.assertFalse(disc.LAST_FETCH_STATUS["solana"]["ok"])

    def test_malformed_bodies_never_raise(self):
        """Invariant: never raises — a 200 with non-JSON text, or JSON of the wrong
        shape, is a failure (recorded), not an exception into the discovery loop."""
        for body in ("<html>cloudflare</html>", [1, 2, 3]):
            with self.subTest(body=body):
                disc.LAST_FETCH_STATUS.clear()
                pools = _run(_with_client(_Feed((200, body)), lambda c: disc.fetch_new_pools(c, "cro")))
                self.assertEqual(pools, [])
                self.assertFalse(disc.LAST_FETCH_STATUS["cro"]["ok"])

    def test_status_is_recorded_per_network(self):
        """Invariant: fetch status recorded — per chain; one chain failing does not
        mark another chain down (or up)."""
        def route(request):
            if "/networks/solana/" in str(request.url):
                return httpx.Response(500, text="boom")
            return httpx.Response(200, json=_new_pools_body("0xP"))

        async def both(c):
            await disc.fetch_new_pools(c, "cro")
            await disc.fetch_new_pools(c, "solana")

        _run(_with_client(_Feed(route), both))
        self.assertTrue(disc.LAST_FETCH_STATUS["cro"]["ok"])
        self.assertFalse(disc.LAST_FETCH_STATUS["solana"]["ok"])


def _multi_body(prices):
    return {"data": [{"attributes": {"address": a, "base_token_price_usd": str(p)}} for a, p in prices.items()]}


class TestFetchPoolPrices(_Isolated):
    def test_429_backs_off_then_prices(self):
        """Invariant: 429 backoff — a 429 is retried after a 1s backoff and the
        prices of the retried call are returned (both address cases)."""
        feed = _Feed((429, {}), (200, _multi_body({"SoLPoolAbc": 1.25})))
        prices = _run(_with_client(feed, lambda c: disc.fetch_pool_prices(c, "solana", ["SoLPoolAbc"])))
        self.assertEqual(prices, {"SoLPoolAbc": 1.25, "solpoolabc": 1.25})
        self.assertEqual(self.slept(), [1.0])

    def test_persistent_429_returns_empty_and_logs(self):
        """Invariant: 429 backoff (bounded) + never raises + failure recorded (the
        exit-pricing feed records failures in the log; an empty dict = 'hold')."""
        feed = _Feed((429, {}))
        with self.assertLogs(level="WARNING") as logs:
            prices = _run(_with_client(feed, lambda c: disc.fetch_pool_prices(c, "cro", ["0xA"])))
        self.assertEqual(prices, {})
        self.assertEqual(self.slept(), [1.0, 2.0, 4.0])
        self.assertTrue(any("429" in m for m in logs.output))

    def test_transport_exception_never_raises_and_logs(self):
        """Invariant: never raises + failure recorded (log) — a dead network gives
        an empty price map, which the paper engine treats as 'hold'."""
        feed = _Feed(httpx.ReadTimeout("slow"))
        with self.assertLogs(level="WARNING") as logs:
            prices = _run(_with_client(feed, lambda c: disc.fetch_pool_prices(c, "cro", ["0xA", "0xB"])))
        self.assertEqual(prices, {})
        self.assertTrue(any("pools/multi failed" in m for m in logs.output))

    def test_one_failed_chunk_keeps_the_other_chunks(self):
        """Invariant: never raises → partial result. 60 addresses = 2 calls (50 + 10);
        a 500 on the first chunk is logged and the second chunk's prices still
        arrive."""
        addrs = [f"0x{i:040x}" for i in range(60)]

        def route(request):
            n = len(request.url.path.rsplit("/", 1)[-1].split(","))
            if n == 50:
                return httpx.Response(500, text="boom")
            return httpx.Response(200, json=_multi_body({addrs[55]: 2.0}))

        feed = _Feed(route)
        with self.assertLogs(level="WARNING") as logs:
            prices = _run(_with_client(feed, lambda c: disc.fetch_pool_prices(c, "cro", addrs)))
        self.assertEqual(len(feed.requests), 2)
        self.assertEqual(prices.get(addrs[55]), 2.0)
        self.assertTrue(any("HTTP 500" in m for m in logs.output))

    def test_malformed_body_never_raises(self):
        """Invariant: never raises — a non-JSON 200 yields {} (hold), not a crash."""
        prices = _run(_with_client(_Feed((200, "not json")),
                                   lambda c: disc.fetch_pool_prices(c, "cro", ["0xA"])))
        self.assertEqual(prices, {})

    def test_no_addresses_makes_no_call(self):
        """Invariant support: no open positions → no request spent from the
        shared 30-calls/min GeckoTerminal budget."""
        feed = _Feed((200, _multi_body({})))
        self.assertEqual(_run(_with_client(feed, lambda c: disc.fetch_pool_prices(c, "cro", []))), {})
        self.assertEqual(feed.requests, [])


if __name__ == "__main__":
    unittest.main()
