# One-step launcher (start_bot.py, 2026-11-04) — offline, Telegram mocked.

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import start_bot as sb

FAKE_TOKEN = "123456789:" + "A" * 35


class TestPureHelpers(unittest.TestCase):
    def test_upsert_keeps_comments_replaces_and_appends(self):
        text = "# hello\nTELEGRAM_BOT_TOKEN=old\nOTHER=1\n"
        out = sb.upsert_env_text(text, {"TELEGRAM_BOT_TOKEN": "new", "TELEGRAM_CHAT_ID": "42"})
        self.assertEqual(out, "# hello\nTELEGRAM_BOT_TOKEN=new\nOTHER=1\nTELEGRAM_CHAT_ID=42\n")

    def test_read_env(self):
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write('# c\nA=1\nB="two"\n\n')
        try:
            self.assertEqual(sb.read_env(f.name), {"A": "1", "B": "two"})
        finally:
            os.unlink(f.name)
        self.assertEqual(sb.read_env("/nonexistent/.env"), {})

    def test_find_private_chat_takes_newest_private(self):
        payload = {"ok": True, "result": [
            {"update_id": 5, "message": {"chat": {"id": -100, "type": "group"}}},
            {"update_id": 6, "message": {"chat": {"id": 42, "type": "private",
                                                    "first_name": "Loukas", "username": "lf"}}},
        ]}
        self.assertEqual(sb.find_private_chat(payload), ("42", "Loukas (@lf)", 6))
        self.assertIsNone(sb.find_private_chat({"ok": False}))
        self.assertIsNone(sb.find_private_chat({"ok": True, "result": []}))

    def test_token_format(self):
        self.assertTrue(sb.token_looks_valid(FAKE_TOKEN))
        self.assertFalse(sb.token_looks_valid("hello"))
        self.assertFalse(sb.token_looks_valid(""))


class _FakeResp:
    def __init__(self, data):
        self._d = data

    def json(self):
        return self._d


class _FakeClient:
    """Answers getMe / getWebhookInfo / getUpdates / sendMessage like Telegram."""

    def __init__(self, webhook=""):
        self.calls = []
        self.webhook = webhook

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, json=None, timeout=None):
        method = url.rsplit("/", 1)[-1]
        self.calls.append((method, json))
        if method == "getMe":
            return _FakeResp({"ok": True, "result": {"username": "defi_test_bot"}})
        if method == "getWebhookInfo":
            return _FakeResp({"ok": True, "result": {"url": self.webhook}})
        if method == "getUpdates":
            return _FakeResp({"ok": True, "result": [
                {"update_id": 1, "message": {"chat": {"id": 777, "type": "private", "first_name": "Owner"}}}]})
        return _FakeResp({"ok": True, "result": {}})


class TestSetupFlow(unittest.TestCase):
    def test_first_run_saves_token_and_detected_chat_and_greets(self):
        d = tempfile.mkdtemp()
        env_path = os.path.join(d, ".env")
        fake = _FakeClient()
        answers = iter([FAKE_TOKEN, "y", ""])  # token, "is that you?", skip wallet
        with mock.patch.object(sb, "ENV_PATH", env_path), \
                mock.patch("httpx.Client", lambda: fake), \
                mock.patch("builtins.input", lambda prompt="": next(answers)), \
                mock.patch("builtins.print"):
            extra = sb.setup()
        self.assertEqual(extra, [])
        env = sb.read_env(env_path)
        self.assertEqual(env["TELEGRAM_BOT_TOKEN"], FAKE_TOKEN)
        self.assertEqual(env["TELEGRAM_CHAT_ID"], "777")
        sends = [j for m, j in fake.calls if m == "sendMessage"]
        self.assertEqual(sends[0]["chat_id"], "777")  # the owner gets a message immediately

    def test_bot_used_elsewhere_is_not_taken_without_consent(self):
        d = tempfile.mkdtemp()
        fake = _FakeClient(webhook="https://other.example/hook")
        answers = iter([FAKE_TOKEN, "n"])
        with mock.patch.object(sb, "ENV_PATH", os.path.join(d, ".env")), \
                mock.patch("httpx.Client", lambda: fake), \
                mock.patch("builtins.input", lambda prompt="": next(answers)), \
                mock.patch("builtins.print"):
            with self.assertRaises(SystemExit):
                sb.setup()
        self.assertNotIn("deleteWebhook", [m for m, _ in fake.calls])

    def test_existing_env_starts_without_questions(self):
        d = tempfile.mkdtemp()
        env_path = os.path.join(d, ".env")
        with open(env_path, "w") as f:
            f.write(f"TELEGRAM_BOT_TOKEN={FAKE_TOKEN}\nTELEGRAM_CHAT_ID=777\nWALLET_ADDRESS=0x{'a' * 40}\n")
        fake = _FakeClient()
        with mock.patch.object(sb, "ENV_PATH", env_path), \
                mock.patch("httpx.Client", lambda: fake), \
                mock.patch("builtins.input", side_effect=AssertionError("must not ask")), \
                mock.patch("builtins.print"):
            self.assertEqual(sb.setup(), [])
        self.assertNotIn("getUpdates", [m for m, _ in fake.calls])


if __name__ == "__main__":
    unittest.main()
