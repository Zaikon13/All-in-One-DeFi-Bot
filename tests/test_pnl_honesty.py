# Part 2 (2026-07-17): a failed transaction fetch must reply "Couldn't fetch
# transaction data right now" — never "No meaningful transactions found today."
# Offline — no network, no env keys.

import asyncio
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("WALLET_ADDRESS", "0x1234567890abcdef1234567890abcdef12345678")

import core.pnl_calculator as pnl


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestFetchFailurePath(unittest.TestCase):
    def test_failed_fetch_returns_unavailable_not_empty(self):
        async def fail_get(client, path, params=None, full=False):
            return None  # HTTP error / 429 / rejected key

        nf = mock.AsyncMock()
        with mock.patch.object(pnl, "explorer_get", side_effect=fail_get), \
             mock.patch.object(pnl, "check_data_freshness", new=mock.AsyncMock()), \
             mock.patch.object(pnl, "note_fetch_failure", new=nf):
            data = _run(pnl.calculate_daily_pnl_async())
            nf.assert_awaited()  # failure counts as stale (throttled alert)

        self.assertTrue(data.get("unavailable"))
        self.assertIn("error", data)

    def test_report_says_unavailable_never_no_transactions(self):
        async def fake_calc():
            return {"error": "data source unavailable", "unavailable": True,
                    "date": "2026-07-17", "tokens": []}

        with mock.patch.object(pnl, "calculate_daily_pnl_async", side_effect=fake_calc):
            report = _run(pnl.get_daily_pnl_report())

        self.assertIn("Couldn't fetch transaction data right now", report)
        self.assertNotIn("No meaningful transactions", report)

    def test_genuinely_empty_day_still_reports_no_transactions(self):
        # successful fetch, zero of today's transactions -> the classic line stays
        async def fake_calc():
            return {"date": "2026-07-17", "tokens": []}

        with mock.patch.object(pnl, "calculate_daily_pnl_async", side_effect=fake_calc):
            report = _run(pnl.get_daily_pnl_report())

        self.assertIn("No meaningful transactions", report)
        self.assertNotIn("Couldn't fetch", report)

    def test_partial_failure_marks_unavailable(self):
        # first endpoint returns one good page then the second endpoint fails
        calls = {"n": 0}

        async def flaky_get(client, path, params=None, full=False):
            calls["n"] += 1
            if path == "account/getTxsByAddress":
                return {"result": [], "pagination": {}}
            return None  # CRC-20 endpoint down

        with mock.patch.object(pnl, "explorer_get", side_effect=flaky_get), \
             mock.patch.object(pnl, "check_data_freshness", new=mock.AsyncMock()), \
             mock.patch.object(pnl, "note_fetch_failure", new=mock.AsyncMock()):
            txs, ok = _run(pnl.get_today_transactions_async())

        self.assertFalse(ok)  # incomplete data must not masquerade as a quiet day


if __name__ == "__main__":
    unittest.main()
