# Webhook self-heal (2026-07-18) — offline tests for the pure drift/resolve logic
# and the read-back discipline of ensure_webhook. No network.

import asyncio
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.telegram_webhook as tw

BOT = "https://bot-production-3d9c.up.railway.app/telegram/webhook"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestResolveWebhookUrl(unittest.TestCase):
    def test_explicit_webhook_url_wins(self):
        self.assertEqual(
            tw.resolve_webhook_url("https://x.example/telegram/webhook", "https://y.example", "z.example"),
            "https://x.example/telegram/webhook")

    def test_app_url_gets_path_appended(self):
        self.assertEqual(tw.resolve_webhook_url(None, "https://y.example", None),
                         "https://y.example/telegram/webhook")
        self.assertEqual(tw.resolve_webhook_url(None, "https://y.example/", None),
                         "https://y.example/telegram/webhook")

    def test_already_suffixed_base_not_doubled(self):
        self.assertEqual(tw.resolve_webhook_url(None, "https://y.example/telegram/webhook", None),
                         "https://y.example/telegram/webhook")

    def test_railway_domain_without_scheme(self):
        self.assertEqual(tw.resolve_webhook_url(None, None, "bot-production-3d9c.up.railway.app"),
                         BOT)

    def test_default_canonical(self):
        self.assertEqual(tw.resolve_webhook_url(None, None, None), tw.CANONICAL_WEBHOOK_URL)
        self.assertEqual(tw.resolve_webhook_url("", "  ", None), tw.CANONICAL_WEBHOOK_URL)


class TestNeedsRestore(unittest.TestCase):
    def test_match_no_restore(self):
        self.assertFalse(tw.needs_restore({"url": BOT}, BOT))
        self.assertFalse(tw.needs_restore({"ok": True, "result": {"url": BOT}}, BOT))

    def test_drift_restores(self):
        self.assertTrue(tw.needs_restore(
            {"url": "https://web-gpl6-production.up.railway.app/telegram/webhook"}, BOT))

    def test_empty_url_is_drift(self):
        self.assertTrue(tw.needs_restore({"url": ""}, BOT))
        self.assertTrue(tw.needs_restore({}, BOT))

    def test_none_payload_is_not_drift(self):
        self.assertFalse(tw.needs_restore(None, BOT))
        self.assertFalse(tw.needs_restore("junk", BOT))


class TestEnsureWebhookReadback(unittest.TestCase):
    """ensure_webhook must never claim success without a confirming read-back."""

    def _ensure(self, infos, set_ok):
        seq = list(infos)

        async def fake_info(client, token):
            return seq.pop(0) if seq else None

        async def fake_set(client, token, url, drop_pending=False):
            return set_ok

        with mock.patch.object(tw, "get_webhook_info", side_effect=fake_info), \
             mock.patch.object(tw, "set_webhook", side_effect=fake_set):
            return _run(tw.ensure_webhook(None, "tok", BOT))

    def test_already_ok(self):
        self.assertEqual(self._ensure([{"url": BOT}], True), "ok")

    def test_drift_restored_and_confirmed(self):
        drifted = {"url": "https://dead.example/telegram/webhook"}
        self.assertEqual(self._ensure([drifted, {"url": BOT}], True), "restored")

    def test_set_succeeds_but_readback_disagrees_is_failed(self):
        drifted = {"url": "https://dead.example/telegram/webhook"}
        self.assertEqual(self._ensure([drifted, drifted], True), "failed")

    def test_set_rejected_is_failed(self):
        drifted = {"url": "https://dead.example/telegram/webhook"}
        self.assertEqual(self._ensure([drifted], False), "failed")

    def test_unreadable_state_is_skipped_never_blind_set(self):
        self.assertEqual(self._ensure([None], True), "skipped")


if __name__ == "__main__":
    unittest.main()
