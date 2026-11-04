# Critical-function tests (docs/CRITICAL_FUNCTIONS.md, Tier 4):
#   worker.py `scheduled_eod_pnl`, `scheduled_scan_digest` — the daily messages.
#   Invariant: fire once per Athens day at the configured time, also across DST.
# Offline, no real time: a virtual UTC clock replaces worker.datetime, and the
# patched asyncio.sleep advances that clock by the requested seconds. After N
# sleeps it raises a sentinel that ends the `while True` loop; the test then
# asserts on what was sent before it.

import asyncio
import os
import sys
import unittest
from collections import Counter
from datetime import datetime, timedelta, timezone
from unittest import mock
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import worker
from core import paper_trading as paper

ATHENS = ZoneInfo("Europe/Athens")


class _StopLoop(BaseException):
    """Sentinel from the patched sleep; BaseException so no `except Exception` eats it."""


def _athens(y, mo, d, h, mi=0, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=ATHENS)


class _VirtualTime:
    """worker.datetime + asyncio.sleep over one virtual clock.
    early_s simulates the wall clock being early_s behind the sleep (an NTP step
    back / early wake): the clock advances by (requested - early_s)."""

    def __init__(self, start, max_sleeps, early_s=0.0):
        self.now = start.astimezone(timezone.utc)
        self.max_sleeps = max_sleeps
        self.early_s = early_s
        self.sleeps = []
        self.sent = []  # (athens wall time, text)
        self.send_results = []  # scripted send_telegram results (then True)
        self.eod_state_at_send = []  # worker.last_eod_run as seen by each send
        clock = self

        class FakeDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return clock.now.astimezone(tz) if tz else clock.now.replace(tzinfo=None)

        self.datetime = FakeDateTime

    async def sleep(self, seconds, *a, **k):
        if len(self.sleeps) >= self.max_sleeps:
            raise _StopLoop()
        self.sleeps.append(seconds)
        self.now += timedelta(seconds=seconds - self.early_s)

    async def send(self, text):
        self.sent.append((self.now.astimezone(ATHENS), text))
        self.eod_state_at_send.append(worker.last_eod_run)
        return self.send_results.pop(0) if self.send_results else True

    def run(self, coro_fn):
        patches = [mock.patch.object(worker, "datetime", self.datetime),
                   mock.patch.object(worker.asyncio, "sleep", new=self.sleep),
                   mock.patch.object(worker, "send_telegram", new=self.send)]
        for p in patches:
            p.start()
        loop = asyncio.new_event_loop()
        try:
            try:
                loop.run_until_complete(coro_fn())
            except _StopLoop:
                pass
        finally:
            loop.close()
            for p in reversed(patches):
                p.stop()
        return self.sent


# ------------------------------------------------------------------ EOD report

class _EodHarness(unittest.TestCase):
    def setUp(self):
        self.report = mock.AsyncMock(return_value="REPORT-BODY")
        patches = [
            mock.patch.dict(os.environ, {"EOD_PNL_ENABLED": "true", "EOD_PNL_HOUR": "23",
                                         "EOD_PNL_MINUTE": "55", "MARKET_ANALYSIS_ENABLED": "false"}),
            mock.patch.object(worker, "last_eod_run", None),
            mock.patch.object(worker, "save_known_pairs", new=mock.MagicMock()),
            mock.patch.object(paper, "PAPER_TRADING_ENABLED", False),
            # string target = lazy import: never be the first importer of core.pnl_calculator
            mock.patch("core.pnl_calculator.get_daily_pnl_report", new=self.report),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def reports(self, sent):
        return [(t, m) for t, m in sent if "Automatic end-of-day wallet report" in m]

    def assert_once_per_day_at(self, sent, days, hour, minute):
        self.assertEqual([t.date() for t, _ in sent], days)
        for t, _ in sent:
            self.assertEqual((t.hour, t.minute), (hour, minute), t)


class TestEodSchedule(_EodHarness):
    def test_fires_once_per_day_at_2355_across_spring_forward(self):
        """Invariant: once per Athens day at the configured time, also across DST.
        Athens springs forward 2026-03-29 03:00→04:00 (that day is 23h long).
        Mutation that breaks it: computing the sleep as local wall-clock arithmetic
        (target - now_local) — the Mar 29 report then fires at 00:55 on Mar 30."""
        vt = _VirtualTime(_athens(2026, 3, 26, 12), max_sleeps=6)
        sent = self.reports(vt.run(worker.scheduled_eod_pnl))
        days = [datetime(2026, 3, d).date() for d in range(26, 32)]
        self.assert_once_per_day_at(sent, days, 23, 55)
        self.assertTrue(all("REPORT-BODY" in m for _, m in sent))

    def test_fires_once_per_day_at_2355_across_fall_back(self):
        """Invariant: once per Athens day at the configured time, also across DST.
        Athens falls back 2026-10-25 04:00→03:00 (that day is 25h long)."""
        vt = _VirtualTime(_athens(2026, 10, 23, 9), max_sleeps=5)
        sent = self.reports(vt.run(worker.scheduled_eod_pnl))
        days = [datetime(2026, 10, d).date() for d in range(23, 28)]
        self.assert_once_per_day_at(sent, days, 23, 55)

    def test_early_wake_does_not_double_send(self):
        """Invariant: ONCE per Athens day. If the wall clock is 2s behind the sleep
        (early wake), the loop wakes at 23:54:58, sends, then re-wakes 60s later
        at 23:55:56 — the 22h last_eod_run guard must suppress that second send.
        Mutation that breaks it: removing the `delta_s < 22 * 3600` guard."""
        vt = _VirtualTime(_athens(2026, 6, 10, 12), max_sleeps=8, early_s=2.0)
        sent = self.reports(vt.run(worker.scheduled_eod_pnl))
        per_day = Counter(t.date() for t, _ in sent)
        self.assertGreaterEqual(len(per_day), 3)
        self.assertEqual(set(per_day.values()), {1}, sent)

    def test_restart_just_after_a_send_waits_for_the_next_day(self):
        """Invariant: once per Athens day — a restart two minutes after tonight's
        send (last_eod_run persisted) does not send again tonight."""
        sent_at = _athens(2026, 6, 10, 23, 55)
        with mock.patch.object(worker, "last_eod_run", sent_at.astimezone(timezone.utc).isoformat()):
            vt = _VirtualTime(_athens(2026, 6, 10, 23, 57), max_sleeps=1)
            sent = self.reports(vt.run(worker.scheduled_eod_pnl))
        self.assert_once_per_day_at(sent, [datetime(2026, 6, 11).date()], 23, 55)

    def test_report_failure_does_not_kill_the_loop(self):
        """Invariant: the daily message keeps firing — a failed report sends the
        failure notice and the NEXT day's report still goes out."""
        self.report.side_effect = [RuntimeError("explorer down"), "REPORT-BODY"]
        vt = _VirtualTime(_athens(2026, 6, 10, 12), max_sleeps=2)
        sent = vt.run(worker.scheduled_eod_pnl)
        self.assertEqual(len(sent), 2)
        self.assertIn("report failed", sent[0][1])
        self.assertIn("REPORT-BODY", sent[1][1])
        self.assertEqual(sent[1][0].date(), datetime(2026, 6, 11).date())

    def test_undelivered_report_is_retried_once_then_recorded(self):
        """Round 2 TG2: EOD state only on delivery. A rejected send is retried once
        300 s later; the retry's success sets last_eod_run. Mutation that breaks
        it: ignoring send_telegram's result (no retry)."""
        vt = _VirtualTime(_athens(2026, 6, 10, 12), max_sleeps=2)
        vt.send_results = [False, True]
        sent = self.reports(vt.run(worker.scheduled_eod_pnl))
        # the 23:55 report, then its one retry 300 s later (00:00 Athens)
        self.assertEqual([t for t, _ in sent], [_athens(2026, 6, 10, 23, 55), _athens(2026, 6, 11, 0, 0)])
        self.assertEqual(sent[0][1], sent[1][1])
        self.assertEqual(vt.sleeps[-1], 300)
        self.assertIsNotNone(worker.last_eod_run)
        worker.save_known_pairs.assert_called_once()

    def test_report_never_delivered_is_not_recorded_as_sent(self):
        """Round 2 TG2: two rejected sends → last_eod_run stays None (not saved),
        and the next day's report still goes out. Mutation that breaks it:
        setting last_eod_run before/regardless of the send result."""
        vt = _VirtualTime(_athens(2026, 6, 10, 12), max_sleeps=3)
        vt.send_results = [False, False]
        with self.assertLogs("worker", level="ERROR") as logs:
            sent = self.reports(vt.run(worker.scheduled_eod_pnl))
        # 23:55 send + its 300 s retry (both rejected), then the next day's report
        self.assertEqual([t for t, _ in sent], [_athens(2026, 6, 10, 23, 55), _athens(2026, 6, 11, 0, 0),
                                                _athens(2026, 6, 11, 23, 55)])
        self.assertEqual(vt.eod_state_at_send, [None, None, None])  # day 1 never recorded
        self.assertTrue(any("EOD report NOT delivered" in m for m in logs.output), logs.output)
        self.assertEqual(worker.save_known_pairs.call_count, 1)    # only day 2's delivery

    def test_disabled_never_sends(self):
        """Invariant support: EOD_PNL_ENABLED=false → the loop idles, never sends."""
        with mock.patch.dict(os.environ, {"EOD_PNL_ENABLED": "false"}):
            vt = _VirtualTime(_athens(2026, 6, 10, 12), max_sleeps=3)
            self.assertEqual(vt.run(worker.scheduled_eod_pnl), [])
        self.report.assert_not_called()


# ------------------------------------------------------------- scanner digest

class _DigestHarness(unittest.TestCase):
    def setUp(self):
        patches = [
            mock.patch.object(worker, "SCAN_DIGEST_ENABLED", True),
            mock.patch.object(worker, "SCAN_DIGEST_HOUR", 21),
            mock.patch.object(worker, "chain_stats", {}),
            mock.patch.dict(os.environ, {"CHAINS_ENABLED": "cro"}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def digests(self, sent):
        return [(t, m) for t, m in sent if "Scanner digest" in m]


class TestScanDigestSchedule(_DigestHarness):
    def test_fires_once_per_day_at_2100_across_spring_forward(self):
        """Invariant: once per Athens day at the configured time, also across DST
        (spring-forward 2026-03-29). Mutation that breaks it: wall-clock sleep
        arithmetic — the Mar 29 digest would fire at 22:00 instead of 21:00."""
        vt = _VirtualTime(_athens(2026, 3, 27, 8), max_sleeps=4)
        sent = self.digests(vt.run(worker.scheduled_scan_digest))
        self.assertEqual([t.date() for t, _ in sent], [datetime(2026, 3, d).date() for d in range(27, 31)])
        self.assertTrue(all((t.hour, t.minute) == (21, 0) for t, _ in sent), sent)

    def test_fires_once_per_day_at_2100_across_fall_back(self):
        """Invariant: once per Athens day at the configured time, also across DST
        (fall-back 2026-10-25)."""
        vt = _VirtualTime(_athens(2026, 10, 24, 22), max_sleeps=3)
        sent = self.digests(vt.run(worker.scheduled_scan_digest))
        self.assertEqual([t.date() for t, _ in sent], [datetime(2026, 10, d).date() for d in (25, 26, 27)])
        self.assertTrue(all((t.hour, t.minute) == (21, 0) for t, _ in sent), sent)

    def test_each_digest_covers_its_own_day(self):
        """Invariant: one digest per day — the counters roll at each send, so a
        day's numbers are reported once, never again in the next digest."""
        worker.chain_stats["cro"] = {"seen": 5, "matured": 3, "passed": 1, "sent": 1,
                                     "best_score": 71.0, "best_symbol": "MOON"}
        vt = _VirtualTime(_athens(2026, 6, 10, 12), max_sleeps=2)
        sent = self.digests(vt.run(worker.scheduled_scan_digest))
        self.assertIn("seen 5", sent[0][1])
        self.assertIn("seen 0", sent[1][1])
        self.assertEqual(worker.chain_stats, {})

    def test_send_failure_does_not_kill_the_loop(self):
        """Invariant: the digest keeps firing daily — one failed send/format is
        logged and the next day's digest still goes out."""
        real = worker.format_multichain_digest
        fmt = mock.MagicMock(side_effect=[RuntimeError("boom"), real({}, ["cro"])])
        with mock.patch.object(worker, "format_multichain_digest", new=fmt):
            vt = _VirtualTime(_athens(2026, 6, 10, 12), max_sleeps=2)
            sent = self.digests(vt.run(worker.scheduled_scan_digest))
        self.assertEqual([t.date() for t, _ in sent], [datetime(2026, 6, 11).date()])

    def test_disabled_returns_without_sending(self):
        """Invariant support: SCAN_DIGEST_ENABLED=false → returns, never sends."""
        with mock.patch.object(worker, "SCAN_DIGEST_ENABLED", False):
            vt = _VirtualTime(_athens(2026, 6, 10, 12), max_sleeps=3)
            self.assertEqual(vt.run(worker.scheduled_scan_digest), [])
        self.assertEqual(vt.sleeps, [])

    def test_early_wake_does_not_double_send(self):
        """Invariant: ONCE per Athens day. Same scenario the EOD loop survives: the
        wall clock is 2s behind the sleep, so the loop wakes at 20:59:58.
        Was a BUG (fixed round 2, TGd3: in-memory 22h guard): scheduled_scan_digest sent unconditionally after every
        sleep and has no once-per-day guard (scheduled_eod_pnl has last_eod_run).
        The next sleep is max(60, 2s) = 60s, so a SECOND digest goes out at
        21:00:56 the same evening — every day the clock runs early."""
        vt = _VirtualTime(_athens(2026, 6, 10, 12), max_sleeps=6, early_s=2.0)
        sent = self.digests(vt.run(worker.scheduled_scan_digest))
        per_day = Counter(t.date() for t, _ in sent)
        self.assertEqual(set(per_day.values()), {1}, sent)


if __name__ == "__main__":
    unittest.main()
