# Critical-function tests (docs/CRITICAL_FUNCTIONS.md, Tier 4):
#   worker.py `portfolio_watch` — the price-move alert loop.
#   Invariant: first sighting only seeds; cooldown respected; never alerts on restart.
# Offline: core.wallet.get_wallet_balances is mocked per cycle; a virtual UTC clock
# replaces worker.datetime and the patched asyncio.sleep advances it. The loop is
# stopped by a sentinel raised from the sleep after the scripted cycles.

import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import worker

START = datetime(2026, 11, 4, 9, 0, tzinfo=timezone.utc)


class _StopLoop(BaseException):
    """Sentinel from the patched sleep; BaseException so no `except Exception` eats it."""


def _bal(**prices):
    """A priced get_wallet_balances result: 100 units of each token at `price`."""
    return {"ok": True, "priced": True, "cro": 0.0, "cro_usd": None, "tokens": {},
            "token_details": [{"symbol": s, "contract": f"0x{s.lower()}", "amount": 100.0,
                               "usd": 100.0 * p} for s, p in prices.items()]}


UNPRICED = {"ok": True, "priced": False, "cro": 0.0, "cro_usd": None, "tokens": {}, "token_details": []}


class _WatchHarness(unittest.TestCase):
    def setUp(self):
        self.now = START
        patches = [
            mock.patch.object(worker, "PORTFOLIO_WATCH_ENABLED", True),
            mock.patch.object(worker, "WALLET_ADDRESS", "0xWALLET"),
            mock.patch.object(worker, "PORTFOLIO_WATCH_INTERVAL_MIN", 5.0),
            mock.patch.object(worker, "PORTFOLIO_MOVE_THRESHOLD_PCT", 10.0),
            mock.patch.object(worker, "PORTFOLIO_MIN_USD", 5.0),
            mock.patch.object(worker, "PORTFOLIO_ALERT_COOLDOWN_MIN", 60.0),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def run_watch(self, cycles):
        """One portfolio_watch run (= one worker process lifetime) over `cycles`,
        each a balances dict or an Exception. Returns [(cycle_index, text)]."""
        harness = self
        clock_cls = type("FakeDateTime", (datetime,), {
            "now": classmethod(lambda cls, tz=None: harness.now.astimezone(tz) if tz
                               else harness.now.replace(tzinfo=None))})
        state = {"cycle": 0}
        sent = []

        async def fake_sleep(seconds, *a, **k):
            state["cycle"] += 1
            if state["cycle"] >= len(cycles):
                raise _StopLoop()
            harness.now += timedelta(seconds=seconds)

        async def rec(text):
            sent.append((state["cycle"], text))

        balances = mock.AsyncMock(side_effect=list(cycles))
        patches = [mock.patch.object(worker, "datetime", clock_cls),
                   mock.patch.object(worker.asyncio, "sleep", new=fake_sleep),
                   mock.patch.object(worker, "send_telegram", new=rec),
                   mock.patch("core.wallet.get_wallet_balances", new=balances)]
        for p in patches:
            p.start()
        loop = asyncio.new_event_loop()
        try:
            with self.assertRaises(_StopLoop):
                loop.run_until_complete(worker.portfolio_watch())
        finally:
            loop.close()
            for p in reversed(patches):
                p.stop()
        self.assertEqual(balances.await_count, len(cycles))      # every cycle really ran
        return sent


class TestPortfolioWatchLoop(_WatchHarness):
    def test_first_sighting_only_seeds(self):
        """Invariant: first sighting only seeds. Cycle 1 sees WOOF for the first
        time → no alert, however large; an unchanged price after → no alert.
        Mutation that breaks it: alerting when baseline is missing (base=None)."""
        sent = self.run_watch([_bal(WOOF=1.0), _bal(WOOF=1.0), _bal(WOOF=1.05)])
        self.assertEqual(sent, [])

    def test_new_token_mid_run_only_seeds(self):
        """Invariant: first sighting only seeds — per holding: a token that appears
        in cycle 3 seeds silently even though another token is already tracked."""
        sent = self.run_watch([_bal(WOOF=1.0), _bal(WOOF=1.0), _bal(WOOF=1.0, NEWT=9.0),
                               _bal(WOOF=1.0, NEWT=9.0)])
        self.assertEqual(sent, [])

    def test_restart_never_alerts(self):
        """Invariant: never alerts on restart. Run 1 tracks WOOF at $1. The worker
        restarts (a new portfolio_watch run) and WOOF is now $3 (+200%): the first
        cycles of run 2 only re-seed — no alert. Mutation that breaks it: keeping
        the baseline at module level / on disk without a restart seed."""
        self.assertEqual(self.run_watch([_bal(WOOF=1.0), _bal(WOOF=1.0)]), [])
        self.assertEqual(self.run_watch([_bal(WOOF=3.0), _bal(WOOF=3.0)]), [])

    def test_move_alerts_then_cooldown_is_respected(self):
        """Invariant: cooldown respected. Cycles are 5 min apart, cooldown 60 min.
        +20% at cycle 1 alerts (baseline rebases to $1.20). A further +25% at
        cycle 2 is inside the cooldown → silent. The first cycle ≥ 60 min after
        the alert (cycle 13) alerts again. Mutation that breaks it: dropping the
        `(now_utc - la) < cooldown` check (alerts at cycle 2)."""
        cycles = [_bal(WOOF=1.0), _bal(WOOF=1.2)] + [_bal(WOOF=1.5)] * 12
        sent = self.run_watch(cycles)
        self.assertEqual([i for i, _ in sent], [1, 13], sent)
        self.assertIn("+20.0%", sent[0][1])
        self.assertIn("+25.0%", sent[1][1])

    def test_all_movers_in_one_message(self):
        """Invariant support: one cycle's movers share ONE message (not one per token)."""
        sent = self.run_watch([_bal(WOOF=1.0, MOON=2.0), _bal(WOOF=1.5, MOON=1.0)])
        self.assertEqual(len(sent), 1)
        self.assertIn("WOOF", sent[0][1])
        self.assertIn("MOON", sent[0][1])

    def test_failed_cycles_skip_and_keep_the_baseline(self):
        """Invariant: first sighting only seeds — a failed fetch (exception) and an
        unpriced cycle are skipped without re-seeding, so a real +25% move vs the
        ORIGINAL baseline still alerts afterwards, and the loop never dies.
        Mutation that breaks it: removing the loop's try/except (dies at cycle 1)."""
        sent = self.run_watch([_bal(WOOF=1.0), RuntimeError("explorer 429"), UNPRICED,
                               _bal(WOOF=1.25)])
        self.assertEqual([i for i, _ in sent], [3], sent)
        self.assertIn("+25.0%", sent[0][1])

    def test_disabled_or_no_wallet_returns_without_polling(self):
        """Invariant support: off-switch / no wallet → the loop returns at once and
        never fetches balances (it cannot alert at all)."""
        balances = mock.AsyncMock()
        with mock.patch("core.wallet.get_wallet_balances", new=balances):
            for attr, val in (("PORTFOLIO_WATCH_ENABLED", False), ("WALLET_ADDRESS", None)):
                with mock.patch.object(worker, attr, val):
                    loop = asyncio.new_event_loop()
                    try:
                        loop.run_until_complete(worker.portfolio_watch())
                    finally:
                        loop.close()
        balances.assert_not_called()


if __name__ == "__main__":
    unittest.main()
