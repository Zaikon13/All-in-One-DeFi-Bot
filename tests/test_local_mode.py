# Standalone/local run mode (2026-11-04) — offline. No network.

import asyncio
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")

from core.local_mode import (allowed_chat_ids, extract_updates, is_chat_allowed,
                             normalize_command)


def _run(coro):
    # private loop, never installed as current: asyncio.run() would reset the
    # global loop policy and break other tests that use get_event_loop()
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestPureHelpers(unittest.TestCase):
    def test_normalize_command(self):
        self.assertEqual(normalize_command("/Wallet@MyDefiBot now"), "/wallet")
        self.assertEqual(normalize_command("  /paper "), "/paper")
        self.assertEqual(normalize_command("/grok-analyze"), "/grok-analyze")
        self.assertEqual(normalize_command("hello"), "")
        self.assertEqual(normalize_command(None), "")

    def test_allowlist(self):
        allowed = allowed_chat_ids(" 123, 456 ,")
        self.assertEqual(allowed, {"123", "456"})
        self.assertTrue(is_chat_allowed(123, allowed))
        self.assertFalse(is_chat_allowed("999", allowed))
        self.assertTrue(is_chat_allowed("999", allowed_chat_ids("")))  # no restriction

    def test_configured_allowed_chats_prefers_explicit_list(self):
        from core.local_mode import configured_allowed_chats
        with mock.patch.dict(os.environ, {"TELEGRAM_ALLOWED_CHAT_IDS": "1,2", "TELEGRAM_CHAT_ID": "9"}):
            self.assertEqual(configured_allowed_chats(), {"1", "2"})
        with mock.patch.dict(os.environ, {"TELEGRAM_ALLOWED_CHAT_IDS": "", "TELEGRAM_CHAT_ID": "9"}):
            self.assertEqual(configured_allowed_chats(), {"9"})
        with mock.patch.dict(os.environ, {"TELEGRAM_ALLOWED_CHAT_IDS": "", "TELEGRAM_CHAT_ID": ""}):
            self.assertEqual(configured_allowed_chats(), set())  # empty -> callers fail closed

    def test_extract_updates(self):
        payload = {"ok": True, "result": [
            {"update_id": 10, "message": {"text": "/wallet", "chat": {"id": 1}}},
            {"update_id": 11, "message": {"sticker": {}, "chat": {"id": 1}}},  # no text
            {"update_id": 12, "edited_message": {"text": "/paper", "chat": {"id": 2}}},
            "junk",
        ]}
        ups, nxt = extract_updates(payload, 0)
        self.assertEqual(ups, [("1", "/wallet"), ("2", "/paper")])
        self.assertEqual(nxt, 13)  # offset advances past non-text updates too

    def test_extract_updates_bad_payload(self):
        self.assertEqual(extract_updates({"ok": False}, 5), ([], 5))
        self.assertEqual(extract_updates(None, 5), ([], 5))


class TestConsolePrintRedacts(unittest.TestCase):
    def test_apikey_masked(self):
        import io
        from core.local_mode import console_print
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            console_print("bot", "url ?apikey=SECRET123&x=1", "999")
        out = buf.getvalue()
        self.assertNotIn("SECRET123", out)
        self.assertNotIn("999", out)


class TestHandleCommand(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app.main as main
        cls.main = main

    def _dispatch(self, text):
        sent, scheduled = [], []

        async def fake_send(t, chat_id=None, reply_markup=None):
            sent.append((t, reply_markup))

        with mock.patch.object(self.main, "send_telegram_message", fake_send):
            _run(self.main.handle_command(text, "42", lambda fn, *a: scheduled.append((fn.__name__, a))))
        return sent, scheduled

    def test_start_menu_keyboard_is_rows(self):
        sent, _ = self._dispatch("/start")
        markup = sent[0][1]
        # Telegram rejects a flat list; keyboard must be a list of rows (lists)
        self.assertTrue(all(isinstance(row, list) for row in markup["keyboard"]))

    def test_routing(self):
        cases = {"/wallet": "get_all_balances", "/bal": "get_all_balances",
                 "/paper": "get_paper_status", "/signals": "get_signals",
                 "/daily_pnl": "process_daily_pnl", "/analyze": "process_grok_analyze",
                 "/grok-analyze": "process_grok_analyze", "/Wallet@SomeBot": "get_all_balances"}
        for text, fn in cases.items():
            _, scheduled = self._dispatch(text)
            self.assertEqual(scheduled, [(fn, ("42",))], text)

    def test_unknown(self):
        sent, scheduled = self._dispatch("/nope")
        self.assertIn("Unknown command", sent[0][0])
        self.assertEqual(scheduled, [])

    def test_console_mode_prints_instead_of_sending(self):
        with mock.patch.dict(os.environ, {"CONSOLE_MODE": "true"}), \
                mock.patch("httpx.AsyncClient") as client, \
                mock.patch.object(self.main, "console_print") as cp:
            _run(self.main.send_telegram_message("hi", "1"))
        cp.assert_called_once()
        client.assert_not_called()


class TestInProcessMirror(unittest.TestCase):
    def test_worker_push_sets_bot_mirror_without_http(self):
        import app.main as main
        import worker
        st = {"balance_usd": 1000.0, "starting_usd": 1000.0, "open": [], "closed": []}
        with mock.patch.object(worker, "PAPER_MIRROR_URL", "inprocess"):
            client = mock.MagicMock()
            _run(worker._push_paper_mirror(client, st))
        client.post.assert_not_called()
        self.assertEqual(main.get_paper_mirror()["state"]["balance_usd"], 1000.0)


class TestSignalsFeedHonesty(unittest.TestCase):
    def test_failed_feed_is_flagged_not_shown_as_empty(self):
        from datetime import datetime, timezone
        from app.commands.signals import render_signals
        now = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
        sig = {"chains": ["cro"], "thresholds": {"cro": {"min_liq": 5000, "min_score": 35}},
               "funnel": {"cro": {"seen": 0, "matured": 0, "passed": 0, "sent": 0}},
               "recent": [], "feed": {"cro": {"ok": False}}, "as_of": now.isoformat()}
        self.assertIn("feed unavailable", render_signals(sig, now_utc=now))
        sig["feed"] = {"cro": {"ok": True}}
        self.assertNotIn("feed unavailable", render_signals(sig, now_utc=now))


class TestPollerFailsClosedWithoutAllowList(unittest.TestCase):
    def test_no_chat_id_means_no_command_is_served(self):
        import httpx
        import run_local
        sent, served = [], []

        def handler(request):
            name = request.url.path.rsplit("/", 1)[-1]
            if name == "getWebhookInfo":
                return httpx.Response(200, json={"ok": True, "result": {"url": ""}})
            if name == "getUpdates":
                if served or sent:  # second poll: end the loop deterministically
                    return httpx.Response(409, json={"ok": False})
                return httpx.Response(200, json={"ok": True, "result": [
                    {"update_id": 1, "message": {"text": "/wallet", "chat": {"id": 777}}}]})
            if name == "sendMessage":
                sent.append(request.content.decode())
            return httpx.Response(200, json={"ok": True, "result": {}})

        async def handle(text, chat_id, tasks):
            served.append(text)

        real = httpx.AsyncClient
        with mock.patch.dict(os.environ, {}), \
                mock.patch("httpx.AsyncClient",
                           lambda **kw: real(transport=httpx.MockTransport(handler), **kw)):
            os.environ.pop("TELEGRAM_CHAT_ID", None)
            os.environ.pop("TELEGRAM_ALLOWED_CHAT_IDS", None)
            # the handler's 409 on the second poll ends the loop deterministically
            _run(run_local._telegram_poll_loop(handle, None, "T", False))
        self.assertEqual(served, [])
        self.assertTrue(sent and "TELEGRAM_CHAT_ID=777" in sent[0])


class TestPollerNeverStealsWebhook(unittest.TestCase):
    """A token already served by a webhook (e.g. the Grok-run bot) must make the
    local poller REFUSE, never call deleteWebhook unless explicitly told to."""

    def _run_poll(self, take_over):
        import httpx
        import run_local
        calls = []

        def handler(request):
            calls.append(request.url.path.rsplit("/", 1)[-1])
            if calls[-1] == "getWebhookInfo":
                return httpx.Response(200, json={"ok": True, "result": {"url": "https://other.example/hook"}})
            return httpx.Response(200, json={"ok": True, "result": {}})

        real = httpx.AsyncClient
        with mock.patch("httpx.AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw)):
            async def go():
                await asyncio.wait_for(
                    run_local._telegram_poll_loop(None, None, "T", take_over), timeout=2)
            try:
                _run(go())
            except asyncio.TimeoutError:
                pass
        return calls

    def test_refuses_by_default(self):
        calls = self._run_poll(take_over=False)
        self.assertEqual(calls, ["getWebhookInfo"])
        self.assertNotIn("deleteWebhook", calls)

    def test_take_over_requires_readback(self):
        # read-back still shows the webhook -> must not start polling
        calls = self._run_poll(take_over=True)
        self.assertIn("deleteWebhook", calls)
        self.assertNotIn("getUpdates", calls)

    def test_failed_readback_is_not_confirmation(self):
        """Round 2 TG5: a read-back that is itself an error (429, no result) must
        not count as 'webhook gone'. Mutation that breaks it: reading the url from
        `.get("result") or {}` (an error body then looks like an empty url)."""
        import httpx
        import run_local
        calls, infos = [], [
            {"ok": True, "result": {"url": "https://other.example/hook"}},
            {"ok": False, "error_code": 429, "description": "Too Many Requests"},
        ]

        def handler(request):
            calls.append(request.url.path.rsplit("/", 1)[-1])
            if calls[-1] == "getWebhookInfo":
                return httpx.Response(200, json=infos.pop(0))
            return httpx.Response(200, json={"ok": True, "result": True})

        real = httpx.AsyncClient
        with mock.patch("httpx.AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw)), \
                self.assertLogs("run_local", level="ERROR") as logs:
            async def go():
                await asyncio.wait_for(
                    run_local._telegram_poll_loop(None, None, "T", True), timeout=2)
            _run(go())  # returns (refuses); a timeout here would mean it started polling
        self.assertEqual(calls, ["getWebhookInfo", "deleteWebhook", "getWebhookInfo"])
        self.assertNotIn("getUpdates", calls)
        self.assertTrue(any("not confirmed" in m for m in logs.output), logs.output)


class TestRunnerExitCode(unittest.TestCase):
    """Round 2 RT1: _amain returns the exit code; a crashed or stopped worker /
    poller is logged and exits 1 (never a silent exit 0)."""

    def _amain(self, **patches):
        from argparse import Namespace
        import run_local
        ns = Namespace(no_worker=patches.pop("no_worker", False), selftest=False,
                       take_over_webhook=False)
        ctx = [mock.patch.dict(os.environ, {"CONSOLE_MODE": "false"}),
               mock.patch.object(run_local, "_seed_paper_mirror")]
        ctx += [mock.patch.object(obj, name, new) for obj, name, new in patches.pop("objs", [])]
        for c in ctx:
            c.start()
        try:
            return _run(run_local._amain(ns))
        finally:
            for c in reversed(ctx):
                c.stop()

    def test_worker_crash_exits_1_and_logs(self):
        import run_local
        import worker
        forever_awaited = []

        async def poller(*a, **k):
            forever_awaited.append(1)
            await asyncio.Event().wait()  # never set: only the worker can end _amain

        with self.assertLogs("run_local", level="ERROR") as logs:
            rc = self._amain(objs=[(worker, "main", mock.AsyncMock(side_effect=RuntimeError("boom"))),
                                   (run_local, "_telegram_poll_loop", poller)])
        self.assertEqual(rc, 1)
        self.assertTrue(any("crashed" in m for m in logs.output), logs.output)

    def test_poller_that_returns_exits_1(self):
        import run_local
        with self.assertLogs("run_local", level="ERROR"):
            rc = self._amain(no_worker=True,
                             objs=[(run_local, "_telegram_poll_loop", mock.AsyncMock(return_value=None))])
        self.assertEqual(rc, 1)

    def test_main_exits_with_the_code(self):
        import run_local
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "FAKE_TOKEN"}), \
                mock.patch.object(run_local.asyncio, "run", lambda c: (c.close(), 1)[1]):
            with self.assertRaises(SystemExit) as cm:
                run_local.main([])
        self.assertEqual(cm.exception.code, 1)


class TestLocalDefaults(unittest.TestCase):
    """Round 2 RT2: run_local honours a mounted volume and forces the settings
    polling mode needs. Plain dicts stand in for os.environ."""

    def setUp(self):
        import run_local
        self.apply = run_local._apply_local_defaults

    def test_volume_is_honoured(self):
        env = {"RAILWAY_VOLUME_MOUNT_PATH": "/x"}
        self.apply(env)
        self.assertNotIn("WORKER_DATA_DIR", env)

    def test_no_volume_defaults_to_repo_data(self):
        env = {}
        self.apply(env)
        self.assertTrue(env["WORKER_DATA_DIR"].endswith("data"), env)
        self.assertEqual(env["WEBHOOK_AUTOSET_ENABLED"], "false")

    def test_explicit_data_dir_unchanged(self):
        env = {"WORKER_DATA_DIR": "/y"}
        self.apply(env)
        self.assertEqual(env["WORKER_DATA_DIR"], "/y")

    def test_guard_and_mirror_are_forced_with_a_warning(self):
        env = {"WEBHOOK_GUARD_ENABLED": "true",
               "PAPER_MIRROR_URL": "https://old.example/internal/paper-state",
               "WEBHOOK_AUTOSET_ENABLED": "true"}
        with self.assertLogs("run_local", level="WARNING") as logs:
            self.apply(env)
        self.assertEqual(env["WEBHOOK_GUARD_ENABLED"], "false")
        self.assertEqual(env["PAPER_MIRROR_URL"], "inprocess")
        self.assertEqual(env["WEBHOOK_AUTOSET_ENABLED"], "true")  # a default, not forced
        self.assertEqual(len(logs.output), 2, logs.output)
        self.assertFalse(any("old.example" in m for m in logs.output), logs.output)

    def test_paper_state_lands_on_the_volume(self):
        import core.paper_trading as paper
        with mock.patch.dict(os.environ, {"RAILWAY_VOLUME_MOUNT_PATH": "/x"}):
            os.environ.pop("WORKER_DATA_DIR", None)
            self.apply(os.environ)
            self.assertEqual(paper.state_path(), "/x/paper_state.json")


class TestConsolePrintNeverRaises(unittest.TestCase):
    """Round 2 TG4: console_print runs outside the senders' try; a non-UTF-8
    stdout used to raise UnicodeEncodeError and kill the worker at startup."""

    def test_cp1252_stdout_gets_replaced_text(self):
        import io
        from core.local_mode import console_print
        buf = io.BytesIO()
        out = io.TextIOWrapper(buf, encoding="cp1252")
        try:
            with mock.patch("sys.stdout", out):
                console_print("worker", "✅ worker is online ─ 📨")  # must not raise
            out.flush()
            self.assertIn(b"online", buf.getvalue())
        finally:
            out.detach()

    def test_failing_stdout_does_not_raise(self):
        from core.local_mode import console_print

        class _Broken:
            encoding = "utf-8"

            def write(self, s):
                raise OSError("stdout closed")

            def flush(self):
                raise OSError("stdout closed")

        with mock.patch("sys.stdout", _Broken()):
            console_print("bot", "hello")  # must not raise


if __name__ == "__main__":
    unittest.main()
