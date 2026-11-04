# Critical-function tests (docs/CRITICAL_FUNCTIONS.md, Tier 4):
#   core/claude_client.py `call_claude` — AI text.
#   Invariant: timeout; any failure → an error prefix that callers detect.
# "Callers detect" = core.claude_client.is_valid_claude_response (re-exported as
# is_valid_grok_response), the gate app/main.py and core/pnl_calculator.py use.
# Offline: anthropic.AsyncAnthropic is replaced by a recording fake.

import asyncio
import os
import sys
import types
import unittest
from unittest import mock

import anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import claude_client as cc

FAKE_KEY = "sk-ant-test-not-real"
GOOD_TEXT = "Net inflow of USDC today; no other token moved."


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _StatusError(anthropic.APIStatusError):
    """An SDK status error without needing the SDK's HTTP response type."""

    def __init__(self, status, message):
        Exception.__init__(self, message)
        self.status_code = status
        self.message = message


class _SdkTimeout(anthropic.APITimeoutError):
    def __init__(self):
        Exception.__init__(self, "Request timed out.")


def _reply(text):
    return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text=text)])


class _ClaudeHarness(unittest.TestCase):
    def setUp(self):
        self.made = []
        self.create = mock.AsyncMock(return_value=_reply(GOOD_TEXT))
        harness = self

        class FakeAsyncAnthropic:
            def __init__(self, **kw):
                harness.made.append(kw)
                self.messages = types.SimpleNamespace(create=harness.create)

        for p in (mock.patch.object(cc, "ANTHROPIC_API_KEY", FAKE_KEY),
                  mock.patch.object(cc.anthropic, "AsyncAnthropic", FakeAsyncAnthropic)):
            p.start()
            self.addCleanup(p.stop)

    def assert_detected_failure(self, out):
        self.assertIsInstance(out, str)
        self.assertTrue(out.startswith(cc.CLAUDE_ERROR_PREFIXES), out)
        self.assertFalse(cc.is_valid_claude_response(out), out)
        self.assertFalse(cc.is_valid_grok_response(out), out)     # the alias callers import


class TestCallClaudeTimeout(_ClaudeHarness):
    def test_timeout_is_forwarded_to_the_sdk_client(self):
        """Invariant: timeout. The caller's timeout reaches the SDK client (the
        default 600s SDK timeout would hang /daily_pnl). Mutation that breaks it:
        dropping `timeout=timeout` from AsyncAnthropic(...)."""
        out = _run(cc.call_claude("prompt", timeout=7.5))
        self.assertEqual(out, GOOD_TEXT)
        self.assertEqual(self.made[0].get("timeout"), 7.5)
        self.assertEqual(self.made[0].get("api_key"), FAKE_KEY)

    def test_default_timeout_is_finite(self):
        """Invariant: timeout — callers that pass none still get a bounded wait."""
        _run(cc.call_claude("prompt"))
        t = self.made[0].get("timeout")
        self.assertIsInstance(t, (int, float))
        self.assertLessEqual(t, 60)

    def test_sdk_timeout_maps_to_detectable_error(self):
        """Invariant: any failure → an error prefix that callers detect (a timeout
        must never raise into the webhook or the EOD loop)."""
        self.create.side_effect = _SdkTimeout()
        self.assert_detected_failure(_run(cc.call_claude("prompt", timeout=1.0)))

    def test_asyncio_timeout_maps_to_detectable_error(self):
        self.create.side_effect = asyncio.TimeoutError()
        self.assert_detected_failure(_run(cc.call_claude("prompt", timeout=1.0)))

    @unittest.expectedFailure
    def test_caller_timeout_is_the_whole_budget(self):
        """Invariant: timeout. Callers treat the value as a HARD bound ("Hard
        timeout (25s) for this command path" in core/pnl_calculator.py, 25s in
        app/main.py to keep the webhook responsive).
        BUG (finding): AsyncAnthropic is built without max_retries, so the SDK
        default (anthropic.DEFAULT_MAX_RETRIES == 2) retries a timed-out request:
        the timeout is per attempt and a 25s "hard" timeout can take ~3 x 25s plus
        backoff. Fix: max_retries=0 (or an overall deadline); if fixed with a
        deadline wrapper instead, update this test to assert that."""
        _run(cc.call_claude("prompt", timeout=25.0))
        kw = self.made[0]
        attempts = 1 + kw.get("max_retries", anthropic.DEFAULT_MAX_RETRIES)
        self.assertEqual(attempts, 1, f"{attempts} attempts x {kw.get('timeout')}s timeout each")


class TestCallClaudeFailuresAreDetectable(_ClaudeHarness):
    def test_missing_key_is_detectable_and_makes_no_call(self):
        """Invariant: any failure → detectable error prefix — no key configured."""
        with mock.patch.object(cc, "ANTHROPIC_API_KEY", None):
            out = _run(cc.call_claude("prompt"))
        self.assert_detected_failure(out)
        self.assertEqual(self.made, [])

    def test_api_status_error_is_detectable(self):
        """Invariant: any failure → detectable error prefix — an HTTP 529/401 from
        Anthropic. Mutation that breaks it: returning str(e) without the prefix."""
        self.create.side_effect = _StatusError(529, "overloaded")
        out = _run(cc.call_claude("prompt"))
        self.assert_detected_failure(out)
        self.assertIn("529", out)

    def test_unexpected_exception_is_detectable(self):
        """Invariant: any failure → detectable error prefix — never raises."""
        self.create.side_effect = RuntimeError("socket closed")
        self.assert_detected_failure(_run(cc.call_claude("prompt")))

    def test_malformed_response_is_detectable(self):
        """Invariant: any failure → detectable error prefix — a reply with no text
        block (empty content / a non-text block) is a failure, not a crash."""
        for reply in (types.SimpleNamespace(content=[]),
                      types.SimpleNamespace(content=[types.SimpleNamespace(type="tool_use")])):
            with self.subTest(reply=reply):
                self.create.return_value = reply
                self.assert_detected_failure(_run(cc.call_claude("prompt")))

    def test_success_passes_the_gate(self):
        """Invariant (other side): a real answer is NOT mistaken for a failure."""
        out = _run(cc.call_claude("prompt"))
        self.assertEqual(out, GOOD_TEXT)
        self.assertTrue(cc.is_valid_claude_response(out))


if __name__ == "__main__":
    unittest.main()
