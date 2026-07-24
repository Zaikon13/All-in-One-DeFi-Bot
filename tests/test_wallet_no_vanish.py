# Part 4 (2026-07-23): a held token must never silently vanish from /wallet
# between calls. Full sweep populates holdings; on an incremental cycle a failed
# read for a held token shows its LAST KNOWN amount (marked stale), never omits.
# Offline — every network seam is mocked.

import asyncio
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.wallet as wallet

W = "0xEa53Dead0000000000000000000000000000dEaD"
# three CRC-20 tokens (contract -> (symbol, decimals, name))
CONTRACTS = {"0xxyo": ("XYO", 18, "XYO"), "0xada": ("ADA", 18, "ADA"),
             "0xcro2": ("TOK", 18, "Token")}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _raw(units):  # human amount -> raw 1e18 string
    return str(int(units * 10**18))


class TestNoVanish(unittest.TestCase):
    def setUp(self):
        wallet._TOKEN_SET_CACHE.clear()

    def _call(self, balances_by_contract):
        """Run get_wallet_balances once with mocked discovery/native/token reads.
        balances_by_contract: {contract: raw_str or None}."""
        async def fake_discover(client, addr):
            w = addr.lower()
            wallet._TOKEN_SET_CACHE.setdefault(
                w, {"contracts": dict(CONTRACTS), "newest_block": 1, "discovered_ts": 9e18})
            return dict(CONTRACTS)

        async def fake_native(client, path, params=None, full=False):
            return {"balance": _raw(1000)}  # native CRO ok

        async def fake_v2(client, params):
            if params.get("action") == "tokenbalance":
                return balances_by_contract.get(params.get("contractaddress"))
            return []

        async def fake_prices(client, contracts):
            return {}  # unpriced -> token_details still built, priced=False path

        with mock.patch.object(wallet, "_discover_token_set", side_effect=fake_discover), \
             mock.patch.object(wallet, "explorer_get", side_effect=fake_native), \
             mock.patch.object(wallet, "_v2_get", side_effect=fake_v2), \
             mock.patch.object(wallet, "get_token_prices", side_effect=fake_prices), \
             mock.patch.object(wallet, "check_data_freshness", new=mock.AsyncMock()):
            return _run(wallet.get_wallet_balances(W))

    def test_full_sweep_then_failed_incremental_keeps_token(self):
        # Force fresh full sweep, then an immediate incremental.
        os.environ["WALLET_BALANCE_REFRESH_HOURS"] = "6"
        # 1) full sweep — all three read OK
        r1 = self._call({"0xxyo": _raw(120000), "0xada": _raw(40), "0xcro2": _raw(9000)})
        syms1 = {d["symbol"] for d in r1["token_details"]}
        self.assertEqual(syms1, {"XYO", "ADA", "TOK"})
        self.assertTrue(r1["ok"])

        # 2) incremental — XYO's read FAILS (429 -> None); ADA/TOK ok
        r2 = self._call({"0xxyo": None, "0xada": _raw(40), "0xcro2": _raw(9000)})
        syms2 = {d["symbol"] for d in r2["token_details"]}
        self.assertIn("XYO", syms2, "held token must NOT vanish on a failed incremental read")
        xyo = next(d for d in r2["token_details"] if d["symbol"] == "XYO")
        self.assertEqual(xyo["amount"], 120000.0)   # last-known amount carried
        self.assertTrue(xyo["stale"])               # marked as carried/last-known
        # ADA refreshed this cycle -> not stale
        ada = next(d for d in r2["token_details"] if d["symbol"] == "ADA")
        self.assertFalse(ada["stale"])

    def test_confirmed_zero_does_drop(self):
        os.environ["WALLET_BALANCE_REFRESH_HOURS"] = "6"
        self._call({"0xxyo": _raw(120000), "0xada": _raw(40), "0xcro2": _raw(9000)})
        # ADA genuinely sold -> successful read of 0 -> it SHOULD leave
        r2 = self._call({"0xxyo": _raw(120000), "0xada": _raw(0), "0xcro2": _raw(9000)})
        syms = {d["symbol"] for d in r2["token_details"]}
        self.assertNotIn("ADA", syms)
        self.assertIn("XYO", syms)

    def tearDown(self):
        os.environ.pop("WALLET_BALANCE_REFRESH_HOURS", None)
        wallet._TOKEN_SET_CACHE.clear()


class TestStaleMarkerRender(unittest.TestCase):
    def test_render_marks_stale(self):
        from app.commands.balances import _render_usd
        bal = {"cro": 1000.0, "cro_usd": 81.0, "usd_total": 93.0,
               "tokens": {"XYO": 120000.0},
               "token_details": [
                   {"symbol": "XYO", "contract": "0xa", "amount": 120000.0, "usd": 51.0, "stale": True},
                   {"symbol": "ADA", "contract": "0xb", "amount": 40.0, "usd": 17.0, "stale": False}],
               "priced": True, "ok": True}
        out = _render_usd(W, bal)
        self.assertIn("XYO", out)
        self.assertIn("last known", out)          # stale token marked
        self.assertIn("ADA", out)
        # ADA line has no 'last known'
        ada_line = [l for l in out.splitlines() if "ADA" in l][0]
        self.assertNotIn("last known", ada_line)


if __name__ == "__main__":
    unittest.main()
