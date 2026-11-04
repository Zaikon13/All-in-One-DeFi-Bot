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


if __name__ == "__main__":
    unittest.main()
