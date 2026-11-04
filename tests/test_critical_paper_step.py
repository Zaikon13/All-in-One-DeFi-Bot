# Critical-function tests (docs/CRITICAL_FUNCTIONS.md, Tier 3):
#   worker.py `_paper_step` — the simulation engine.
#   Invariant: a paper bug never breaks the scanner; one note per entry and per exit.
# Offline: paper state I/O, the price feed, the mirror push and Telegram are mocked.
# The scanner-level tests run ONE real poll_new_pools cycle and stop it with a
# sentinel raised from the patched asyncio.sleep.

import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import worker
from core import paper_trading as paper
from core import pair_discovery as disc

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
_RealAsyncClient = httpx.AsyncClient


class _StopLoop(BaseException):
    """Sentinel from the patched sleep; BaseException so no `except Exception` eats it."""


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _pool(addr, chain="solana", price="1.0", sym="MOON"):
    return {"chain": chain, "pairAddress": addr,
            "baseToken": {"symbol": sym, "address": f"Tok{addr}"},
            "quoteToken": {"symbol": "SOL"}, "priceUsd": price}


def _fresh(*pools_and_scores):
    return [(p, 50_000.0, 2.0, {"score": s}) for p, s in pools_and_scores]


def _open_pos(addr="PoolOpen1", chain="solana", entry=1.0, opened=NOW - timedelta(hours=1)):
    return {"chain": chain, "pair_address": addr, "symbol": "OPEN/SOL", "token_address": f"tok{addr}",
            "entry_price": entry, "qty": 50.0 / entry, "usd_in": 50.0, "score": 80.0,
            "opened_at": opened.isoformat(), "flags": {}}


class _PaperHarness(unittest.TestCase):
    """Pins the engine config to the documented defaults and mocks every seam."""

    def setUp(self):
        self.sent = []

        async def rec(text):
            self.sent.append(text)

        self.prices = mock.AsyncMock(return_value={})
        self.state = paper.fresh_state()
        self.load = mock.MagicMock(side_effect=lambda *a, **k: self.state)
        self.mirror = mock.AsyncMock()
        patches = [
            mock.patch.object(worker, "paper_state", None),
            mock.patch.object(worker, "send_telegram", new=rec),
            mock.patch.object(worker, "_push_paper_mirror", new=self.mirror),
            mock.patch.object(worker, "LIQ_SANITY_BLOCK_PAPER_ENTRY", True),
            mock.patch.object(worker, "HONEYPOT_BLOCK_PAPER_ENTRY", False),
            mock.patch.object(disc, "fetch_pool_prices", new=self.prices),
            mock.patch.object(paper, "PAPER_TRADING_ENABLED", True),
            mock.patch.object(paper, "load_state", new=self.load),
            mock.patch.object(paper, "save_state", new=mock.MagicMock(return_value=True)),
            mock.patch.object(paper, "PAPER_ENTRY_SCORE", 70.0),
            mock.patch.object(paper, "PAPER_POSITION_USD", 50.0),
            mock.patch.object(paper, "PAPER_MAX_OPEN", 5),
            mock.patch.object(paper, "PAPER_TP_PCT", 25.0),
            mock.patch.object(paper, "PAPER_SL_PCT", 15.0),
            mock.patch.object(paper, "PAPER_MAX_HOLD_HOURS", 24.0),
            mock.patch.object(paper, "PAPER_MAX_TICK_RATIO", 10.0),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def step(self, fresh, now=NOW):
        _run(worker._paper_step(object(), fresh, now))

    def buys(self):
        return [m for m in self.sent if "PAPER BUY" in m]

    def sells(self):
        return [m for m in self.sent if "PAPER SELL" in m]


class TestOneNotePerEntryAndExit(_PaperHarness):
    def test_one_note_per_entry_none_for_skips(self):
        """Invariant: one note per entry. Two 🔥 pools → two BUY notes; a below-bar
        pool → no note. Mutation that breaks it: sending the note before the
        should_enter check (a note for a skipped pair)."""
        self.step(_fresh((_pool("PoolA"), 80), (_pool("PoolB", chain="cro"), 75), (_pool("PoolC"), 50)))
        self.assertEqual(len(self.buys()), 2)
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(len(self.state["open"]), 2)
        self.assertAlmostEqual(self.state["balance_usd"], 900.0)

    def test_same_pool_twice_in_a_cycle_enters_once(self):
        """Invariant: one note per entry — a duplicate of a pool entered earlier in
        the same cycle (same chain + address) is not a second entry or note.
        Mutation that breaks it: dropping `open_ids.add(dedup_key)` after an entry."""
        self.step(_fresh((_pool("PoolA"), 80), (_pool("PoolA"), 90)))
        self.assertEqual(len(self.buys()), 1)
        self.assertEqual(len(self.state["open"]), 1)

    def test_one_note_per_exit(self):
        """Invariant: one note per exit. A +30% tick closes the position at the
        +25% TP threshold with exactly one SELL note. Mutation that breaks it:
        sending the SELL note inside the per-price loop twice / for held positions."""
        self.state["open"] = [_open_pos("PoolOpen1"), _open_pos("PoolOpen2")]
        self.state["balance_usd"] = 900.0
        self.prices.return_value = {"PoolOpen1": 1.30}          # PoolOpen2: no price → hold
        self.step([])
        self.assertEqual(len(self.sells()), 1)
        self.assertEqual(len(self.sent), 1)
        self.assertIn("take-profit", self.sells()[0])
        self.assertEqual([p["pair_address"] for p in self.state["open"]], ["PoolOpen2"])
        self.assertAlmostEqual(self.state["closed"][-1]["pnl_usd"], 12.5)
        self.assertAlmostEqual(self.state["balance_usd"], 900.0 + 62.5)

    def test_entry_and_exit_in_one_cycle_are_two_notes(self):
        """Invariant: one note per entry AND one per exit, in the same cycle."""
        self.state["open"] = [_open_pos("PoolOld")]
        self.state["balance_usd"] = 950.0
        self.prices.return_value = {"PoolOld": 0.5}             # -50% → stop-loss
        self.step(_fresh((_pool("PoolNew"), 85)))
        self.assertEqual((len(self.buys()), len(self.sells())), (1, 1))
        self.assertEqual(len(self.sent), 2)
        self.assertIn("stop-loss", self.sells()[0])

    def test_missing_price_and_bad_tick_send_nothing(self):
        """Invariant: one note per exit — and none without an exit. A missing price
        and an absurd (>10× entry) tick both HOLD silently."""
        self.state["open"] = [_open_pos("PoolNoPrice"), _open_pos("PoolGlitch")]
        self.prices.return_value = {"PoolGlitch": 50.0}
        self.step([])
        self.assertEqual(self.sent, [])
        self.assertEqual(len(self.state["open"]), 2)
        self.assertEqual(self.state["closed"], [])

    def test_exits_priced_once_per_chain_not_per_position(self):
        """Invariant: a paper bug never breaks the scanner — exit pricing shares the
        scanner's 30-calls/min GeckoTerminal budget, so it is ONE call per chain,
        never one per position."""
        self.state["open"] = [_open_pos("S1"), _open_pos("S2"), _open_pos("C1", chain="cro")]
        self.step([])
        chains = sorted(c.args[1] for c in self.prices.await_args_list)
        self.assertEqual(chains, ["cro", "solana"])

    def test_disabled_engine_does_nothing(self):
        """Invariant: a paper bug never breaks the scanner — when disabled, the
        engine never even loads state."""
        with mock.patch.object(paper, "PAPER_TRADING_ENABLED", False):
            self.step(_fresh((_pool("PoolA"), 95)))
        self.assertEqual(self.sent, [])
        self.load.assert_not_called()


class TestPaperBugIsContained(_PaperHarness):
    def test_state_load_crash_does_not_raise(self):
        """Invariant: a paper bug never breaks the scanner — a crash inside the
        engine is logged, never raised to the caller. Mutation that breaks it:
        removing _paper_step's try/except."""
        self.load.side_effect = RuntimeError("corrupt beyond repair")
        with self.assertLogs("worker", level="ERROR") as logs:
            self.step(_fresh((_pool("PoolA"), 90)))
        self.assertEqual(self.sent, [])
        self.assertTrue(any("scanner unaffected" in m for m in logs.output))

    def test_price_feed_crash_does_not_raise(self):
        """Invariant: a paper bug never breaks the scanner — even if the exit price
        feed raises (it is documented never to)."""
        self.state["open"] = [_open_pos("PoolOpen1")]
        self.prices.side_effect = RuntimeError("feed exploded")
        self.step([])  # must not raise
        self.assertEqual(len(self.state["open"]), 1)


def _qualifying_norm(now):
    """A mature, deep, busy cro pool that scores 100 (alert + 🔥 paper entry)."""
    pool = {"id": "cro_0xpoolhot", "type": "pool",
            "attributes": {"address": "0xPoolHot", "name": "HOT / WCRO", "base_token_price_usd": "0.02",
                           "reserve_in_usd": "100000",
                           "pool_created_at": (now - timedelta(hours=2)).isoformat(),
                           "volume_usd": {"h1": "40000"}, "price_change_percentage": {"h1": "45"},
                           "transactions": {"h1": {"buys": 90, "sells": 10}}},
            "relationships": {"base_token": {"data": {"id": "cro_0xhot"}},
                              "quote_token": {"data": {"id": "cro_0xwcro"}},
                              "dex": {"data": {"id": "vvs"}}}}
    inc = {"cro_0xhot": {"id": "cro_0xhot", "attributes": {"address": "0xhot", "symbol": "HOT"}},
           "cro_0xwcro": {"id": "cro_0xwcro", "attributes": {"address": "0xwcro", "symbol": "WCRO"}}}
    return disc.parse_gt_pool(pool, "cro", inc)


def _offline_client(**kw):
    def refuse(request):
        raise httpx.ConnectError(f"offline test: unexpected request to {request.url}")
    kw.pop("transport", None)
    return _RealAsyncClient(transport=httpx.MockTransport(refuse), **kw)


class TestScannerSurvivesPaperBug(_PaperHarness):
    def _one_cycle(self):
        norm = _qualifying_norm(datetime.now(timezone.utc))
        patches = [
            mock.patch.object(worker, "chains_enabled", lambda: ["cro"]),
            mock.patch.object(worker, "fetch_new_pools", new=mock.AsyncMock(return_value=[norm])),
            mock.patch.object(worker, "pending_pools", {}),
            mock.patch.object(worker, "seen_pairs", set()),
            mock.patch.object(worker, "pair_last_seen", {}),
            mock.patch.object(worker, "recent_signals", []),
            mock.patch.object(worker, "signals_state", {}),
            mock.patch.object(worker, "chain_stats", {}),
            mock.patch.object(worker, "save_known_pairs", new=mock.MagicMock()),
            mock.patch.object(worker, "save_pending_pools", new=mock.MagicMock()),
            mock.patch.object(worker, "PAIR_MIN_SCORE", 35.0),
            mock.patch.object(worker.httpx, "AsyncClient", _offline_client),
            mock.patch.object(worker.asyncio, "sleep", new=mock.AsyncMock(side_effect=_StopLoop())),
            mock.patch.dict(os.environ, {"PAIR_MIN_LIQUIDITY_USD_CRO": "5000", "PAIR_MIN_SCORE_CRO": ""}),
        ]
        for p in patches:
            p.start()
        try:
            with self.assertRaises(_StopLoop):
                _run(worker.poll_new_pools())
        finally:
            for p in reversed(patches):
                p.stop()

    def test_cycle_sends_one_alert_and_one_paper_note(self):
        """Invariant: one note per entry — at the scanner level a 🔥 pool yields ONE
        pool alert and ONE paper BUY note in the cycle."""
        self._one_cycle()
        alerts = [m for m in self.sent if "New Pool Detected" in m]
        self.assertEqual(len(alerts), 1, self.sent)
        self.assertEqual(len(self.buys()), 1, self.sent)

    def test_pool_alert_still_sent_when_paper_engine_crashes(self):
        """Invariant: a paper bug never breaks the scanner. The engine runs BEFORE
        the cycle's alert is sent; if a paper exception escaped, the alert would be
        lost to the loop's 'Discovery error' handler. Mutation that breaks it:
        removing _paper_step's try/except."""
        with mock.patch.object(paper, "should_enter", side_effect=RuntimeError("paper bug")) as se:
            self._one_cycle()
        se.assert_called()                                         # the engine really ran
        alerts = [m for m in self.sent if "New Pool Detected" in m]
        self.assertEqual(len(alerts), 1, self.sent)
        self.assertEqual(self.buys(), [])


if __name__ == "__main__":
    unittest.main()
