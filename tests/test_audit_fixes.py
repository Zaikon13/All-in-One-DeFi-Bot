# Fixes from the full audit (2026-11-04) — offline, every network seam mocked.

import asyncio
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")

from core.tg_format import (legacy_markdown_balanced, plain_text, split_message,
                            to_tg_markdown)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _Resp:
    def __init__(self, code=200):
        self.status_code = code


class _FakeClient:
    """Records Telegram posts; answers with the given status codes in order."""

    def __init__(self, codes=None):
        self.posts, self.codes = [], list(codes or [])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, **kw):
        self.posts.append(json)
        return _Resp(self.codes.pop(0) if self.codes else 200)


# --- Telegram formatting --------------------------------------------------------

class TestTelegramFormat(unittest.TestCase):
    def test_double_asterisk_becomes_legacy_bold(self):
        self.assertEqual(to_tg_markdown("**Balance:** $5"), "*Balance:* $5")

    def test_plain_text_strips_markers_and_escapes(self):
        self.assertEqual(plain_text("**x** `y` /daily\\_pnl"), "x y /daily_pnl")

    def test_split_respects_limit_and_lines(self):
        text = "\n".join(f"line {i} " + "x" * 50 for i in range(300))
        chunks = split_message(text, limit=1000)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= 1000 for c in chunks))
        self.assertEqual("\n".join(chunks), text)  # nothing lost, split on newlines

    def test_split_hard_cuts_a_monster_line(self):
        chunks = split_message("y" * 2500, limit=1000)
        self.assertEqual([len(c) for c in chunks], [1000, 1000, 500])

    def test_short_message_untouched(self):
        self.assertEqual(split_message("hi"), ["hi"])

    def test_balance_checker(self):
        self.assertTrue(legacy_markdown_balanced("**a** /daily\\_pnl [x](https://a_b.c)"))
        self.assertFalse(legacy_markdown_balanced("/daily_pnl report"))  # lone '_' -> 400

    def test_static_bot_messages_parse(self):
        import app.main as main
        self.assertTrue(legacy_markdown_balanced(main.START_MENU),
                        "/start menu must parse (a bare '/daily_pnl' 400'd it before)")
        src = open(os.path.join(os.path.dirname(main.__file__), "commands", "balances.py")).read()
        self.assertNotIn('"❌ WALLET_ADDRESS not set."', src)


class TestBotSender(unittest.TestCase):
    def setUp(self):
        import app.main as main
        self.main = main

    def _send(self, text, codes=None, markup=None):
        fake = _FakeClient(codes)
        with mock.patch.dict(os.environ, {"CONSOLE_MODE": "false"}), \
                mock.patch.object(self.main, "BOT_TOKEN", "T"), \
                mock.patch("httpx.AsyncClient", lambda **kw: fake):
            _run(self.main.send_telegram_message(text, "1", reply_markup=markup))
        return fake.posts

    def test_converts_bold_for_telegram(self):
        posts = self._send("**Hi**")
        self.assertEqual(posts[0]["text"], "*Hi*")
        self.assertEqual(posts[0]["parse_mode"], "Markdown")

    def test_long_message_is_split_and_keyboard_only_once(self):
        posts = self._send("\n".join("row " + "z" * 80 for i in range(120)), markup={"k": 1})
        self.assertGreater(len(posts), 1)
        self.assertTrue(all(len(p["text"]) <= 4096 for p in posts))
        self.assertIn("reply_markup", posts[0])
        self.assertTrue(all("reply_markup" not in p for p in posts[1:]))

    def test_markdown_rejection_resends_plain(self):
        posts = self._send("**SYM_X** up", codes=[400, 200])
        self.assertEqual(len(posts), 2)
        self.assertNotIn("parse_mode", posts[1])
        self.assertEqual(posts[1]["text"], "SYM_X up")


class TestWorkerSender(unittest.TestCase):
    def test_worker_converts_and_falls_back(self):
        import worker
        fake = _FakeClient([400, 200])
        with mock.patch.dict(os.environ, {"CONSOLE_MODE": "false"}), \
                mock.patch.object(worker, "TELEGRAM_BOT_TOKEN", "T"), \
                mock.patch.object(worker, "TELEGRAM_CHAT_ID", "1"), \
                mock.patch("httpx.AsyncClient", lambda **kw: fake):
            _run(worker.send_telegram("🚀 **New Pool** a_b"))
        self.assertEqual(fake.posts[0]["text"], "🚀 *New Pool* a_b")
        self.assertEqual(fake.posts[1]["text"], "🚀 New Pool a_b")


# --- Worker defaults ---------------------------------------------------------------

class TestWorkerDefaults(unittest.TestCase):
    def test_heartbeat_is_opt_in(self):
        import worker
        with mock.patch.object(worker, "HEARTBEAT_ENABLED", False), \
                mock.patch.object(worker, "send_telegram", new=mock.AsyncMock()) as st:
            _run(worker.heartbeat())  # returns at once instead of looping
        st.assert_not_called()

    def test_eod_defaults_cover_the_day(self):
        import worker
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EOD_PNL_HOUR", None)
            os.environ.pop("EOD_PNL_MINUTE", None)
            self.assertEqual(worker.eod_pnl_time(), (23, 55))
        with mock.patch.dict(os.environ, {"EOD_PNL_HOUR": "99", "EOD_PNL_MINUTE": "x"}):
            self.assertEqual(worker.eod_pnl_time(), (23, 55))
        with mock.patch.dict(os.environ, {"EOD_PNL_HOUR": "22", "EOD_PNL_MINUTE": "30"}):
            self.assertEqual(worker.eod_pnl_time(), (22, 30))

    def test_eod_enabled_defaults_to_wallet_presence(self):
        import worker
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EOD_PNL_ENABLED", None)
            with mock.patch.object(worker, "WALLET_ADDRESS", "0xabc"):
                self.assertTrue(worker.eod_pnl_enabled())
            with mock.patch.object(worker, "WALLET_ADDRESS", None):
                self.assertFalse(worker.eod_pnl_enabled())
        with mock.patch.dict(os.environ, {"EOD_PNL_ENABLED": "false"}), \
                mock.patch.object(worker, "WALLET_ADDRESS", "0xabc"):
            self.assertFalse(worker.eod_pnl_enabled())


# --- Wallet ----------------------------------------------------------------------------

W = "0xEa53Dead0000000000000000000000000000dEaD"


class TestRawBalanceParse(unittest.TestCase):
    def test_numbers_and_errors(self):
        from core.wallet import parse_raw_balance
        self.assertEqual(parse_raw_balance("120000000000000000000"), 120 * 10**18)
        self.assertEqual(parse_raw_balance(" 0 "), 0)
        self.assertEqual(parse_raw_balance(5), 5)
        for bad in ("Max rate limit reached", "", None, "-3", "1.5", True, {"x": 1}):
            self.assertIsNone(parse_raw_balance(bad), bad)


class TestErrorTextNeverEvictsHolding(unittest.TestCase):
    def setUp(self):
        import core.wallet as wallet
        self.wallet = wallet
        wallet._TOKEN_SET_CACHE.clear()

    def _call(self, tokenbalance_result):
        wallet = self.wallet
        contracts = {"0xxyo": ("XYO", 18, "XYO")}

        async def fake_discover(client, addr):
            wallet._TOKEN_SET_CACHE.setdefault(
                addr.lower(), {"contracts": dict(contracts), "newest_block": 1, "discovered_ts": 9e18})
            return dict(contracts)

        async def fake_native(client, path, params=None, full=False):
            return {"balance": str(10**18)}

        async def fake_v2(client, params):
            return tokenbalance_result

        with mock.patch.object(wallet, "_discover_token_set", side_effect=fake_discover), \
                mock.patch.object(wallet, "explorer_get", side_effect=fake_native), \
                mock.patch.object(wallet, "_v2_get", side_effect=fake_v2), \
                mock.patch.object(wallet, "get_token_prices", new=mock.AsyncMock(return_value={})), \
                mock.patch.object(wallet, "check_data_freshness", new=mock.AsyncMock()):
            return _run(wallet.get_wallet_balances(W))

    def test_rate_limit_text_keeps_last_known_amount(self):
        r1 = self._call(str(120000 * 10**18))
        self.assertEqual({d["symbol"] for d in r1["token_details"]}, {"XYO"})
        r2 = self._call("Max rate limit reached")  # HTTP 200 + status 0 error text
        xyo = [d for d in r2["token_details"] if d["symbol"] == "XYO"]
        self.assertEqual(len(xyo), 1, "an error string must not count as a confirmed zero")
        self.assertEqual(xyo[0]["amount"], 120000.0)
        self.assertTrue(xyo[0]["stale"])

    def test_real_zero_still_removes(self):
        self._call(str(5 * 10**18))
        r = self._call("0")
        self.assertEqual(r["token_details"], [])


class TestDiscoveryCompleteness(unittest.TestCase):
    def setUp(self):
        import core.wallet as wallet
        self.wallet = wallet
        wallet._TOKEN_SET_CACHE.clear()

    def _rows(self, contract, block):
        return [{"contractAddress": contract, "tokenSymbol": contract.upper(),
                 "tokenDecimal": "18", "tokenName": contract, "blockNumber": str(block)}]

    def test_failed_page_is_retried_not_treated_as_end(self):
        wallet = self.wallet
        state = {"fail_page_2": True}

        async def fake_v2(client, params):
            page = params["page"]
            if page == 1:
                return self._rows("0xaaa", 300)
            if page == 2:
                return "Max rate limit reached" if state["fail_page_2"] else self._rows("0xbbb", 200)
            if page == 3:
                return self._rows("0xccc", 100)
            return []  # true end of history

        with mock.patch.object(wallet, "_v2_get", side_effect=fake_v2):
            first = _run(wallet._discover_token_set(None, W))
            entry = wallet._TOKEN_SET_CACHE[W.lower()]
            self.assertEqual(set(first), {"0xaaa", "0xccc"})
            self.assertFalse(entry["complete"], "a walk with a failed page is not complete")

            # inside the retry window: cached partial set, no re-walk
            self.assertEqual(set(_run(wallet._discover_token_set(None, W))), {"0xaaa", "0xccc"})

            # after the retry window the cold walk runs again and finds the missing token
            state["fail_page_2"] = False
            entry["discovered_ts"] -= wallet.DISCOVERY_RETRY_SECONDS + 1
            again = _run(wallet._discover_token_set(None, W))
        self.assertEqual(set(again), {"0xaaa", "0xbbb", "0xccc"})
        self.assertTrue(wallet._TOKEN_SET_CACHE[W.lower()]["complete"])


# --- /paper ---------------------------------------------------------------------------

class TestPaperLastPrice(unittest.TestCase):
    def test_compact_keeps_last_price_and_renderer_uses_it(self):
        from core.paper_trading import compact_paper_state
        from app.commands.paper import render_paper_status
        now = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
        st = {"balance_usd": 950.0, "starting_usd": 1000.0, "closed": [],
              "open": [{"symbol": "MOON/SOL", "chain": "solana", "pair_address": "PoolAbc",
                        "token_address": "tokabc", "entry_price": 1.0, "qty": 50.0, "usd_in": 50.0,
                        "last_price": 1.2, "last_price_ts": (now - timedelta(minutes=4)).isoformat()}]}
        compact = compact_paper_state(st)
        self.assertEqual(compact["open"][0]["last_price"], 1.2)
        out = render_paper_status({"state": compact, "as_of": now.isoformat()}, prices={}, now_utc=now)
        self.assertIn("as of 4 min ago", out)
        self.assertIn("+10.00 USD", out)
        self.assertNotIn("price unknown", out)


# --- Daily report honesty ---------------------------------------------------------------

class TestDailyReportHonesty(unittest.TestCase):
    def _data(self, net_value):
        return {"date": "2026-11-04", "total_portfolio_value_usd": net_value,
                "tokens": [{"symbol": "CRO", "trades": 2, "net": -10.0, "position_value_usd": net_value,
                            "trades_list": [{"time": "10:00", "type": "SELL", "amount": 10.0, "symbol": "CRO"}]}]}

    def test_reports_say_what_they_measure(self):
        os.environ.setdefault("WALLET_ADDRESS", "0x1234567890abcdef1234567890abcdef12345678")
        import core.pnl_calculator as pnl
        with mock.patch.object(pnl, "WALLET_ADDRESS", "0x1234567890abcdef1234567890abcdef12345678"):
            for report in (pnl.format_pnl_report(self._data(-1.5)),
                           pnl.format_daily_pnl_report(self._data(-1.5), "fine")):
                self.assertIn("not realized profit/loss", report)
                self.assertNotIn("Avg Cost", report)
                self.assertNotIn("Portfolio Value", report)
                self.assertIn("-$1.50", report)  # outflow days are shown, not hidden

    def test_enrichment_case_insensitive_and_negative_total_kept(self):
        import core.pnl_calculator as pnl

        class FakeSvc:
            def get_current_prices(self, symbols):
                return {s.upper(): 0.1 for s in symbols}

            def close(self):
                pass

        data = {"date": "d", "tokens": [{"symbol": "tWBTC", "net": -2.0, "trades": 1, "trades_list": []}]}
        with mock.patch.object(pnl, "PriceService", FakeSvc):
            out = pnl._enrich_with_current_prices(data)
        self.assertAlmostEqual(out["tokens"][0]["position_value_usd"], -0.2)
        self.assertNotIn("avg_cost_usd", out["tokens"][0])
        self.assertAlmostEqual(out["total_portfolio_value_usd"], -0.2)

    def test_price_service_never_guesses_unknown_ids(self):
        from core.price_service import PriceService
        svc = PriceService()
        try:
            with mock.patch.object(svc.client, "get") as get:
                prices = svc.get_current_prices(["SOMESCAM", "XYO"])
            get.assert_not_called()  # nothing known -> no request, no fake numbers
            self.assertEqual(prices, {"SOMESCAM": None, "XYO": None})
        finally:
            svc.close()


# --- CI hygiene ------------------------------------------------------------------------

class TestHealthCheckWorkflow(unittest.TestCase):
    def test_no_schedule_and_dedup(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            ".github", "workflows", "claude-health-check.yml")
        src = open(path).read()
        self.assertNotIn("cron:", src, "a scheduled check against a down service spams issues")
        self.assertIn('startsWith("Health check:")', src)


if __name__ == "__main__":
    unittest.main()
