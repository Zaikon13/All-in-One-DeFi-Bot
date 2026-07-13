# Part B (2026-07-13): a failed/429/rejected balance fetch must report failure
# honestly, never "$0 / no tokens found". Offline — no network, no env keys needed.

import asyncio
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.wallet as wallet


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestWalletFetchHonesty(unittest.TestCase):
    def test_native_failure_returns_ok_false_not_zeros(self):
        """When the native getBalance call fails (explorer_get -> None), the result
        must be ok=False and must NOT silently proceed to token discovery."""
        async def fake_explorer_get(client, path, params=None, full=False):
            return None  # simulate 429 / rejected key / source down

        async def boom(*a, **k):
            raise AssertionError("token discovery must not run after native failure")

        nf = mock.AsyncMock()
        with mock.patch.object(wallet, "explorer_get", side_effect=fake_explorer_get), \
             mock.patch.object(wallet, "note_fetch_failure", new=nf), \
             mock.patch.object(wallet, "_discover_token_set", side_effect=boom):
            res = _run(wallet.get_wallet_balances("0xabc0000000000000000000000000000000000000"))
            # a failed fetch counts as stale -> the throttled alert path is invoked
            nf.assert_awaited()

        self.assertFalse(res["ok"])
        self.assertEqual(res["cro"], 0.0)
        self.assertEqual(res["tokens"], {})
        self.assertFalse(res["priced"])

    def test_native_failure_marks_stale_via_alert_throttle(self):
        """note_fetch_failure fires the stale alert once and respects the cooldown."""
        wallet._last_stale_alert_ts = 0.0
        sent = []

        async def fake_send(text, client=None):
            sent.append(text)
            return True

        with mock.patch.object(wallet, "send_telegram_alert", side_effect=fake_send):
            _run(wallet.note_fetch_failure())
            _run(wallet.note_fetch_failure())  # immediate second call -> throttled

        self.assertEqual(len(sent), 1)
        self.assertIn("unavailable", sent[0].lower())


class TestBalancesRendererHonesty(unittest.TestCase):
    def _call_with(self, balances_result):
        """Run get_all_balances with get_wallet_balances stubbed to balances_result;
        return the list of messages the command 'sent'."""
        import app.main as main
        from app.commands import balances as bal_cmd
        sent = []

        async def fake_send(text, chat_id=None, reply_markup=None):
            sent.append(text)

        async def fake_get(_addr):
            return balances_result

        with mock.patch.object(main, "WALLET_ADDRESS", "0xEa53Dead0000000000000000000000000000dEaD"), \
             mock.patch.object(main, "send_telegram_message", side_effect=fake_send), \
             mock.patch.object(wallet, "get_wallet_balances", side_effect=fake_get):
            _run(bal_cmd.get_all_balances("123"))
        return sent

    def test_failed_fetch_renders_warning_not_zero(self):
        sent = self._call_with({"ok": False, "cro": 0.0, "tokens": {},
                                "cro_usd": None, "usd_total": None,
                                "token_details": [], "priced": False})
        joined = "\n".join(sent)
        self.assertIn("data source unavailable", joined.lower())
        # must never claim empty/zero on a failure
        self.assertNotIn("No tokens found", joined)
        self.assertNotIn("$0.00", joined)

    def test_ok_fetch_renders_balances_normally(self):
        sent = self._call_with({
            "ok": True, "cro": 1000.0, "cro_usd": 81.0,
            "tokens": {"XYO": 100.0}, "usd_total": 93.0,
            "token_details": [{"symbol": "XYO", "contract": "0xa", "amount": 100.0, "usd": 12.0}],
            "priced": True,
        })
        joined = "\n".join(sent)
        self.assertIn("Wallet Balances", joined)
        self.assertNotIn("data source unavailable", joined.lower())


if __name__ == "__main__":
    unittest.main()