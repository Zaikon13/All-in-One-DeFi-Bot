# Critical-function tests (docs/CRITICAL_FUNCTIONS.md, Tier 4):
#   worker.py `main` (worker.main) — starts every loop via asyncio.gather.
#   Invariant: each loop catches its own errors; one crash doesn't stop the others.
#   worker.py `_supervise` (round 2): a crashed loop is logged and restarted with backoff.
# Offline: persistence, Telegram and every network seam are mocked. No real time:
# loops yield with asyncio.sleep(0) (the real one, captured below) and the test
# drives the event loop for a bounded number of ticks, then cancels everything.

import asyncio
import os
import sys
import unittest
from collections import Counter
from unittest import mock

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import worker
from core import paper_trading as paper

_real_sleep = asyncio.sleep
_RealAsyncClient = httpx.AsyncClient
LOOPS = ("heartbeat", "poll_new_pools", "monitor_wallet", "scheduled_eod_pnl",
         "portfolio_watch", "scheduled_scan_digest", "webhook_guard")


def _drive(coro, ticks=300):
    """Run worker.main as a task for `ticks` loop iterations.
    Returns (main_done, main_exception). Always cancels leftovers and closes."""
    loop = asyncio.new_event_loop()
    try:
        task = loop.create_task(coro)

        async def watch():
            for _ in range(ticks):
                await _real_sleep(0)
                if task.done():
                    return

        loop.run_until_complete(watch())
        done = task.done()
        exc = task.exception() if done and not task.cancelled() else None
        leftovers = asyncio.all_tasks(loop)
        for t in leftovers:
            t.cancel()
        loop.run_until_complete(asyncio.gather(*leftovers, return_exceptions=True))
        return done, exc
    finally:
        loop.close()


def _offline_client(**kw):
    def refuse(request):
        raise httpx.ConnectError(f"offline test: {request.url}")
    kw.pop("transport", None)
    return _RealAsyncClient(transport=httpx.MockTransport(refuse), **kw)


class _MainHarness(unittest.TestCase):
    """Mocks main()'s own startup I/O (persistence load/save, the online message)."""

    def setUp(self):
        self.sent = mock.AsyncMock()
        patches = [
            mock.patch.object(worker, "load_known_pairs", new=mock.MagicMock(return_value=set())),
            mock.patch.object(worker, "load_pending_pools", new=mock.MagicMock(return_value={})),
            mock.patch.object(worker, "save_known_pairs", new=mock.MagicMock()),
            mock.patch.object(worker, "save_pending_pools", new=mock.MagicMock()),
            mock.patch.object(worker, "_volume_configured", new=lambda: True),
            mock.patch.object(worker, "send_telegram", new=self.sent),
            mock.patch.object(worker, "seen_pairs", set()),
            mock.patch.object(worker, "pending_pools", {}),
            mock.patch.object(worker, "last_eod_run", None),
            mock.patch.object(paper, "PAPER_TRADING_ENABLED", False),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def fake_loops(self, crash=None, finish=None):
        """Replace the 7 loops with fakes that tick forever; `crash` raises on its
        first step, `finish` returns at once (a disabled feature)."""
        self.ticks = Counter()

        def make(name):
            async def fake():
                if name == crash:
                    raise RuntimeError(f"{name} crashed")
                if name == finish:
                    return
                while True:
                    self.ticks[name] += 1
                    await _real_sleep(0)
            fake.__name__ = name
            return fake

        return [mock.patch.object(worker, n, new=make(n)) for n in LOOPS]

    def drive_with(self, patches):
        for p in patches:
            p.start()
        try:
            return _drive(worker.main())
        finally:
            for p in reversed(patches):
                p.stop()


class TestWorkerMainSupervision(_MainHarness):
    def test_main_starts_every_loop(self):
        """Invariant: main starts every loop and keeps supervising them. Mutation
        that breaks it: dropping a loop from the asyncio.gather(...) call."""
        done, exc = self.drive_with(self.fake_loops())
        self.assertFalse(done, exc)
        self.assertEqual(set(self.ticks), set(LOOPS))
        self.assertTrue(all(v > 50 for v in self.ticks.values()), self.ticks)
        self.assertIn("online", self.sent.await_args_list[0].args[0])

    def test_a_loop_that_returns_does_not_stop_the_others(self):
        """Invariant: one loop ending (e.g. portfolio-watch disabled, it returns)
        doesn't stop the others or main."""
        done, exc = self.drive_with(self.fake_loops(finish="portfolio_watch"))
        self.assertFalse(done, exc)
        for name in LOOPS:
            if name != "portfolio_watch":
                self.assertGreater(self.ticks[name], 50, name)

    def test_one_crashing_loop_does_not_stop_the_others(self):
        """Invariant: one crash doesn't stop the others.
        Was a BUG (fixed round 2, TGd1: each loop runs under _supervise): main() awaited asyncio.gather(...) WITHOUT
        return_exceptions and without a per-loop supervisor. The first loop
        exception escapes gather, main() raises, and `asyncio.run(main())` (the
        __main__ entry) then cancels every other loop: one crash in any loop (here
        heartbeat, which has no try/except at all) takes down discovery, EOD,
        portfolio-watch, the digest and the webhook guard. The healthy loops are
        still ticking at that moment — main has already exited."""
        done, exc = self.drive_with(self.fake_loops(crash="heartbeat"))
        self.assertFalse(done, f"main() exited ({exc!r}) while the other loops were still alive")

    def test_supervise_restarts_a_crashed_loop(self):
        """Round 2 TGd1: _supervise logs a crash at ERROR, backs off 30 s, then
        restarts the loop; a loop that returns is not restarted. Mutation that
        breaks it: dropping the while-loop (no restart) or the except (crash escapes)."""
        calls = []

        async def factory():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("first run blows up")

        sleep = mock.AsyncMock()
        loop = asyncio.new_event_loop()
        try:
            with mock.patch.object(worker.asyncio, "sleep", new=sleep), \
                    self.assertLogs("worker", level="ERROR") as logs:
                loop.run_until_complete(worker._supervise("x", factory))
        finally:
            loop.close()
        self.assertEqual(len(calls), 2)
        sleep.assert_awaited_once_with(30.0)
        self.assertTrue(any("x crashed" in m for m in logs.output), logs.output)


class TestRealLoopsSurviveTheirOwnFailures(_MainHarness):
    def test_every_loop_keeps_cycling_when_every_seam_fails(self):
        """Invariant: each loop catches its own errors. The REAL loops run under
        main() with every dependency failing — the pool feed, wallet balances, the
        EOD report, the webhook check and all HTTP. Each loop must keep cycling
        (≥3 sleeps) and main must still be running. Mutation that breaks it:
        removing the try/except in any one loop (e.g. portfolio_watch)."""
        cycles = Counter()

        async def fake_sleep(seconds, *a, **k):
            cycles[asyncio.current_task().get_coro().__name__] += 1
            await _real_sleep(0)

        boom = RuntimeError("dependency down")
        patches = [
            mock.patch.dict(os.environ, {"CHAINS_ENABLED": "cro", "EOD_PNL_ENABLED": "true",
                                         "MARKET_ANALYSIS_ENABLED": "false"}),
            mock.patch.object(worker, "HEARTBEAT_ENABLED", True),
            mock.patch.object(worker, "PORTFOLIO_WATCH_ENABLED", True),
            mock.patch.object(worker, "SCAN_DIGEST_ENABLED", True),
            mock.patch.object(worker, "WEBHOOK_GUARD_ENABLED", True),
            mock.patch.object(worker, "WALLET_ADDRESS", "0xWALLETADDRESS"),
            mock.patch.object(worker, "TELEGRAM_BOT_TOKEN", "FAKE_TOKEN"),
            mock.patch.object(worker, "fetch_new_pools", new=mock.AsyncMock(side_effect=boom)),
            mock.patch.object(worker, "ensure_webhook", new=mock.AsyncMock(side_effect=boom)),
            mock.patch("core.wallet.get_wallet_balances", new=mock.AsyncMock(side_effect=boom)),
            mock.patch("core.pnl_calculator.get_daily_pnl_report", new=mock.AsyncMock(side_effect=boom)),
            mock.patch.object(worker.httpx, "AsyncClient", _offline_client),
            mock.patch.object(worker.asyncio, "sleep", new=fake_sleep),
        ]
        with self.assertLogs("worker", level="ERROR"):
            done, exc = self.drive_with(patches)
        self.assertFalse(done, exc)
        for name in LOOPS:
            self.assertGreaterEqual(cycles[name], 3, f"{name} stopped cycling: {dict(cycles)}")


if __name__ == "__main__":
    unittest.main()
