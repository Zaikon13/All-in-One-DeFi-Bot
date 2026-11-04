# Reviewer pass on PR #224 (2026-11-04) — offline. No network, no real env keys.
# One test class per approved work-order step.

import asyncio
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.pnl_calculator as pnl
import core.wallet as wallet

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = "0x1234567890abcdef1234567890abcdef12345678"


def _run(coro):
    # private loop, never installed as current: asyncio.run() would reset the
    # global loop policy and break other tests that use get_event_loop()
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


# --- step 1: endBlock constant ---------------------------------------------------


class TestEndBlockConstant(unittest.TestCase):
    def test_daily_report_fetch_uses_uncapped_end_block(self):
        seen = []

        async def rec(client, path, params=None, full=False):
            seen.append(dict(params or {}))
            return {"result": [], "pagination": {}}

        with mock.patch.object(pnl, "explorer_get", side_effect=rec), \
             mock.patch.object(pnl, "check_data_freshness", new=mock.AsyncMock()), \
             mock.patch.object(pnl, "note_fetch_failure", new=mock.AsyncMock()), \
             mock.patch.object(pnl, "WALLET_ADDRESS", W):
            _run(pnl.get_today_transactions_async())
        self.assertTrue(seen)
        for p in seen:
            self.assertGreaterEqual(p["endBlock"], 2**31 - 1)

    def test_recent_transactions_uses_uncapped_end_block(self):
        seen = []

        async def rec(client, path, params=None, full=False):
            seen.append(dict(params or {}))
            return []

        with mock.patch.object(wallet, "explorer_get", side_effect=rec):
            _run(wallet.get_recent_transactions(W))
        self.assertEqual(len(seen), 2)
        for p in seen:
            self.assertGreaterEqual(p["endBlock"], 2**31 - 1)

    def test_old_literal_is_gone(self):
        for rel in ("core/wallet.py", "core/pnl_calculator.py"):
            self.assertNotIn("99999999", _read(rel), rel)


# --- step 2: webhook chat allow-list (fail closed) --------------------------------


class TestWebhookAllowList(unittest.TestCase):
    def _post(self, chat_id, env):
        import app.main as main
        from fastapi.testclient import TestClient
        hc = mock.AsyncMock()
        with mock.patch.dict(os.environ, env), \
             mock.patch.object(main, "handle_command", hc):
            for k in ("TELEGRAM_CHAT_ID", "TELEGRAM_ALLOWED_CHAT_IDS"):
                if k not in env:
                    os.environ.pop(k, None)
            r = TestClient(main.app).post(
                "/telegram/webhook",
                json={"update_id": 1, "message": {"text": "/wallet", "chat": {"id": chat_id}}})
        return r, hc

    def test_allowed_chat_is_served(self):
        r, hc = self._post(42, {"TELEGRAM_CHAT_ID": "42"})
        self.assertEqual(r.status_code, 200)
        hc.assert_called_once()

    def test_other_chat_is_ignored(self):
        r, hc = self._post(999, {"TELEGRAM_CHAT_ID": "42"})
        self.assertEqual(r.status_code, 200)
        hc.assert_not_called()

    def test_no_allow_list_fails_closed(self):
        r, hc = self._post(42, {})
        self.assertEqual(r.status_code, 200)
        hc.assert_not_called()


# --- step 3: send_telegram_alert console mode + real status ---------------------


class _FakeResp:
    def __init__(self, code):
        self.status_code = code


class _FakeClient:
    """Records posts; answers with the given status codes in order."""

    def __init__(self, codes):
        self.codes = list(codes)
        self.posts = []

    async def post(self, url, json=None, **kw):
        self.posts.append(json)
        return _FakeResp(self.codes.pop(0))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


ALERT_ENV = {"CONSOLE_MODE": "false", "TELEGRAM_BOT_TOKEN": "T", "TELEGRAM_CHAT_ID": "1"}


class TestSendTelegramAlert(unittest.TestCase):
    def test_console_mode_prints_and_never_calls_telegram(self):
        env = dict(ALERT_ENV, CONSOLE_MODE="true")
        with mock.patch.dict(os.environ, env), \
             mock.patch.object(wallet.httpx, "AsyncClient") as ac, \
             mock.patch("core.local_mode.console_print") as cp:
            ok = _run(wallet.send_telegram_alert("⚠️ *stale*"))
        self.assertTrue(ok)
        ac.assert_not_called()
        cp.assert_called_once()

    def test_markdown_rejection_resends_plain(self):
        # both call paths: caller-supplied client= and the function's own client
        for own_client in (False, True):
            with self.subTest(own_client=own_client):
                fc = _FakeClient([400, 200])
                with mock.patch.dict(os.environ, ALERT_ENV), \
                     mock.patch.object(wallet.httpx, "AsyncClient", return_value=fc):
                    ok = _run(wallet.send_telegram_alert("*x*", None if own_client else fc))
                self.assertTrue(ok)
                self.assertEqual(len(fc.posts), 2)
                self.assertIn("parse_mode", fc.posts[0])
                self.assertNotIn("parse_mode", fc.posts[1])

    def test_rejected_twice_returns_false(self):
        for own_client in (False, True):
            with self.subTest(own_client=own_client):
                fc = _FakeClient([400, 400])
                with mock.patch.dict(os.environ, ALERT_ENV), \
                     mock.patch.object(wallet.httpx, "AsyncClient", return_value=fc):
                    ok = _run(wallet.send_telegram_alert("*x*", None if own_client else fc))
                self.assertFalse(ok)


# --- step 4: poller non-200 handling (no hot loop on 401/429) -----------------------


class TestPollerNon200(unittest.TestCase):
    def _poll(self, update_codes):
        import httpx
        import run_local
        codes = list(update_codes)
        calls = []

        def handler(request):
            name = request.url.path.rsplit("/", 1)[-1]
            calls.append(name)
            if name == "getWebhookInfo":
                return httpx.Response(200, json={"ok": True, "result": {"url": ""}})
            if name == "getUpdates":
                code = codes.pop(0) if codes else 409  # 409 always ends the loop
                return httpx.Response(code, json={"ok": False, "error_code": code})
            return httpx.Response(200, json={"ok": True, "result": {}})

        handle = mock.AsyncMock()
        sleep = mock.AsyncMock()
        real = httpx.AsyncClient
        with mock.patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "42"}), \
             mock.patch("httpx.AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw)), \
             mock.patch.object(run_local.asyncio, "sleep", sleep):
            _run(run_local._telegram_poll_loop(handle, None, "T", False))
        return calls, handle, sleep

    def test_429_backs_off_instead_of_hot_looping(self):
        calls, handle, sleep = self._poll([429, 409])  # 409 ends the loop
        self.assertGreaterEqual(sleep.await_count, 1)
        self.assertIn(mock.call(2), sleep.await_args_list)
        handle.assert_not_called()

    def test_401_stops_after_one_get_updates(self):
        calls, handle, sleep = self._poll([401])
        self.assertEqual(calls.count("getUpdates"), 1)
        handle.assert_not_called()


# --- step 5: DST-correct scheduling -------------------------------------------------


class TestSecondsUntilLocal(unittest.TestCase):
    def test_athens_2355_across_dst(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        import worker
        ath = ZoneInfo("Europe/Athens")
        cases = [
            (datetime(2026, 11, 4, 23, 56, tzinfo=ath), 86340),  # normal day
            (datetime(2027, 3, 27, 23, 56, tzinfo=ath), 82740),  # spring forward: 23h day
            (datetime(2026, 10, 24, 23, 56, tzinfo=ath), 89940),  # fall back: 25h day
            (datetime(2026, 11, 4, 10, 0, tzinfo=ath), 50100),   # later the same day
        ]
        for now, expected in cases:
            with self.subTest(now=now.isoformat()):
                self.assertEqual(worker.seconds_until_local(now, 23, 55), expected)


# --- step 6: corrupt paper_state.json is backed up, not lost --------------------


class TestCorruptPaperStateBackup(unittest.TestCase):
    def test_unreadable_file_is_copied_aside_and_survives_next_save(self):
        import glob
        import shutil
        import tempfile
        import core.paper_trading as pt
        for content in (b'{"balance_usd": 1234.5, "open": [', b"[]"):
            with self.subTest(content=content):
                d = tempfile.mkdtemp()
                try:
                    p = os.path.join(d, "paper_state.json")
                    with open(p, "wb") as f:
                        f.write(content)
                    st = pt.load_state(p)
                    self.assertEqual(st, pt.fresh_state())
                    backups = glob.glob(p + ".corrupt-*")
                    self.assertEqual(len(backups), 1)
                    self.assertRegex(backups[0], r"\.corrupt-\d{8}T\d{6}Z$")
                    with open(backups[0], "rb") as f:
                        self.assertEqual(f.read(), content)
                    # the worker saves right after loading: the backup must survive it
                    self.assertTrue(pt.save_state(pt.fresh_state(), p))
                    with open(backups[0], "rb") as f:
                        self.assertEqual(f.read(), content)
                finally:
                    shutil.rmtree(d, ignore_errors=True)

    def test_missing_file_makes_no_backup(self):
        import glob
        import shutil
        import tempfile
        import core.paper_trading as pt
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "paper_state.json")
            pt.load_state(p)
            self.assertEqual(glob.glob(p + ".corrupt-*"), [])
        finally:
            shutil.rmtree(d, ignore_errors=True)


# --- step 7: scam filter on the daily report and /analyze -------------------------


def _crc20_row(symbol, name=None):
    import time
    return {"timestamp": str(int(time.time())), "blockNumber": "100000001",
            "from": {"address": "0x000000000000000000000000000000000000beef"},
            "to": {"address": W}, "value": str(10**18), "error": None,
            "transactionHash": "0xabcdef0123456789",
            "tokenMetadata": {"tokenSymbol": symbol, "decimals": 18, "tokenName": name or symbol}}


class TestScamFilterOutsideWallet(unittest.TestCase):
    def test_daily_report_drops_scam_transfers(self):
        rows = [_crc20_row("claim-usdc.com"), _crc20_row("XYO")]

        async def fake(client, path, params=None, full=False):
            if path == "account/getCRC20TransferByAddress":
                return {"result": rows, "pagination": {}}
            return {"result": [], "pagination": {}}

        with mock.patch.object(pnl, "explorer_get", side_effect=fake), \
             mock.patch.object(pnl, "check_data_freshness", new=mock.AsyncMock()), \
             mock.patch.object(pnl, "note_fetch_failure", new=mock.AsyncMock()), \
             mock.patch.object(pnl, "WALLET_ADDRESS", W):
            txs, ok = _run(pnl.get_today_transactions_async())
        self.assertTrue(ok)
        symbols = [t["contract_ticker_symbol"] for tx in txs for t in tx["transfers"]]
        self.assertEqual(symbols, ["XYO"])

    def test_recent_activity_drops_scam_transfers(self):
        rows = [_crc20_row("claim-usdc.com"), _crc20_row("XYO")]

        async def fake(client, path, params=None, full=False):
            return rows if path == "account/getCRC20TransferByAddress" else []

        with mock.patch.object(wallet, "explorer_get", side_effect=fake):
            out = _run(wallet.get_recent_transactions(W))
        self.assertEqual(len(out), 1)
        self.assertIn("XYO", out[0])
        self.assertFalse(any("claim" in s for s in out))


# --- step 8: /analyze honesty (ok flag + USD ranking) -----------------------------


class TestAnalyzeContext(unittest.TestCase):
    def _ctx(self, balances):
        import app.main as main
        with mock.patch.object(main, "get_wallet_balances", new=mock.AsyncMock(return_value=balances)), \
             mock.patch.object(main, "get_recent_transactions", new=mock.AsyncMock(return_value=[])):
            return _run(main._get_grok_live_context(W))

    def test_outage_is_not_an_empty_wallet(self):
        ctx = self._ctx({"ok": False, "cro": 0.0, "tokens": {}, "cro_usd": None,
                         "usd_total": None, "token_details": [], "priced": False})
        self.assertIn("unavailable", ctx["balances"])
        self.assertNotIn("CRO: 0", ctx["balances"])
        self.assertNotIn("_", ctx["balances"])  # echoed to Telegram in the fallback

    def test_tokens_ranked_by_usd_not_units(self):
        ctx = self._ctx({"ok": True, "cro": 1000.0, "cro_usd": 80.0,
                         "tokens": {"XYO": 120000.0, "TWBTC": 0.002},
                         "token_details": [
                             {"symbol": "XYO", "contract": "0xa", "amount": 120000.0, "usd": 48.0},
                             {"symbol": "TWBTC", "contract": "0xb", "amount": 0.002, "usd": 200.0}],
                         "priced": True})
        lines = ctx["balances"].splitlines()
        self.assertIn("$80.00", lines[0])
        tw = next(i for i, l in enumerate(lines) if "TWBTC" in l)
        xyo = next(i for i, l in enumerate(lines) if "XYO" in l)
        self.assertLess(tw, xyo)
        self.assertIn("$200.00", lines[tw])

    def test_falls_back_to_tokens_dict_without_details(self):
        ctx = self._ctx({"ok": True, "cro": 5.0, "tokens": {"XYO": 10.0}})
        self.assertIn("XYO: 10.0000", ctx["balances"])


# --- step 9: CRO stale price counted once + marked "last known" -------------------


class TestCroStalePrice(unittest.TestCase):
    CONTRACTS = {"0xxyo": ("XYO", 18, "XYO"), "0xada": ("ADA", 18, "ADA")}

    def setUp(self):
        wallet._TOKEN_SET_CACHE.clear()

    def tearDown(self):
        wallet._TOKEN_SET_CACHE.clear()

    def _call(self, price_map):
        contracts = self.CONTRACTS

        async def fake_discover(client, addr):
            wallet._TOKEN_SET_CACHE.setdefault(
                addr.lower(), {"contracts": dict(contracts), "newest_block": 1, "discovered_ts": 9e18})
            return dict(contracts)

        async def fake_native(client, path, params=None, full=False):
            return {"balance": str(1000 * 10**18)}

        async def fake_v2(client, params):
            if params.get("action") == "tokenbalance":
                return {"0xxyo": str(120000 * 10**18),
                        "0xada": str(40 * 10**18)}.get(params.get("contractaddress"))
            return []

        async def fake_prices(client, addrs):
            return dict(price_map)

        with mock.patch.object(wallet, "_discover_token_set", side_effect=fake_discover), \
             mock.patch.object(wallet, "explorer_get", side_effect=fake_native), \
             mock.patch.object(wallet, "_v2_get", side_effect=fake_v2), \
             mock.patch.object(wallet, "get_token_prices", side_effect=fake_prices), \
             mock.patch.object(wallet, "check_data_freshness", new=mock.AsyncMock()), \
             mock.patch.object(wallet, "WALLET_PRICE_MAX_STALE_HOURS", 24.0):
            return _run(wallet.get_wallet_balances(W))

    def test_only_cro_missing_counts_once_and_marks_cro_row(self):
        from app.commands.balances import _render_usd
        wcro = wallet._WCRO_CONTRACT
        r1 = self._call({"0xxyo": 0.0004, "0xada": 0.4, wcro: 0.08})  # cycle 1: all priced
        self.assertEqual(r1["price_stale_count"], 0)
        self.assertFalse(r1["cro_price_stale"])
        r2 = self._call({"0xxyo": 0.0004, "0xada": 0.4})  # cycle 2: only WCRO missing
        self.assertEqual(r2["price_stale_count"], 1)
        self.assertTrue(r2["cro_price_stale"])
        self.assertAlmostEqual(r2["cro_usd"], 80.0)  # last-known CRO price carried
        cro_line = next(l for l in _render_usd(W, r2).splitlines() if "CRO**" in l)
        self.assertIn("last known", cro_line)
        fresh_line = next(l for l in _render_usd(W, r1).splitlines() if "CRO**" in l)
        self.assertNotIn("last known", fresh_line)


# --- step 10: a failed first tokenbalance read is not marked seen -----------------


class TestBalanceSeenOnlyResolved(unittest.TestCase):
    def test_failed_read_is_retried_next_incremental_cycle(self):
        dust = 0.0001
        entry = {"held_set": {"0xa"}, "last_full_ts": 100.0, "balance_seen": {"0xa"}}
        wallet._update_held(entry, ["0xa", "0xfail"], {"0xa": 5.0}, dust, False, 200.0)
        self.assertNotIn("0xfail", entry["balance_seen"])
        self.assertIn("0xa", entry["balance_seen"])
        to_check, is_full = wallet._select_balance_contracts(
            ["0xa", "0xfail"], entry, now=300.0, refresh_seconds=6 * 3600)
        self.assertFalse(is_full)
        self.assertIn("0xfail", to_check)


# --- step 11: CONSOLE_MODE=1 picks the console loop; volume check ----------------


class TestRunnerConsoleFlag(unittest.TestCase):
    def test_console_mode_1_runs_console_loop_not_poller(self):
        from argparse import Namespace
        import run_local
        console = mock.AsyncMock()
        poller = mock.AsyncMock()
        with mock.patch.dict(os.environ, {"CONSOLE_MODE": "1"}), \
             mock.patch.object(run_local, "_console_loop", console), \
             mock.patch.object(run_local, "_telegram_poll_loop", poller), \
             mock.patch.object(run_local, "_seed_paper_mirror"):
            rc = _run(run_local._amain(Namespace(no_worker=True, selftest=False, take_over_webhook=False)))
        console.assert_awaited_once()
        poller.assert_not_called()
        self.assertEqual(rc, 0)  # round 2 RT1: a console loop that ends = clean exit


class TestVolumeConfigured(unittest.TestCase):
    def test_worker_data_dir_alone_counts(self):
        import worker
        with mock.patch.dict(os.environ, {"WORKER_DATA_DIR": "/tmp/x"}):
            os.environ.pop("RAILWAY_VOLUME_MOUNT_PATH", None)
            self.assertTrue(worker._volume_configured())
        with mock.patch.dict(os.environ, {}):
            os.environ.pop("RAILWAY_VOLUME_MOUNT_PATH", None)
            os.environ.pop("WORKER_DATA_DIR", None)
            self.assertFalse(worker._volume_configured())


# --- step 12: report trade times are labelled UTC (the report day is Athens) -------


class TestReportTimesLabelled(unittest.TestCase):
    def test_trade_line_says_utc(self):
        data = {"date": "2026-11-04", "tokens": [
            {"symbol": "XYO", "trades": 1, "net": 1.0,
             "trades_list": [{"time": "12:34", "type": "BUY", "amount": 1.0, "symbol": "XYO"}]}]}
        with mock.patch.object(pnl, "WALLET_ADDRESS", W):
            out = pnl.format_pnl_report(data)
        self.assertIn("12:34 UTC | BUY", out)


if __name__ == "__main__":
    unittest.main()
