# Part 2 (2026-07-24): the portfolio total must not swing because different tokens
# get prices on different cycles. Last-known prices are cached, carried (marked
# stale) when a lookup misses, and still counted — until they expire. Offline.

import asyncio
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.wallet as wallet

W = "0xEa53Dead0000000000000000000000000000dEaD"
CONTRACTS = {"0xxyo": ("XYO", 18, "XYO"), "0xada": ("ADA", 18, "ADA")}
WCRO = wallet._WCRO_CONTRACT


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _raw(u):
    return str(int(u * 10**18))


class TestPriceFlicker(unittest.TestCase):
    def setUp(self):
        wallet._TOKEN_SET_CACHE.clear()

    def tearDown(self):
        wallet._TOKEN_SET_CACHE.clear()
        os.environ.pop("WALLET_BALANCE_REFRESH_HOURS", None)

    def _call(self, price_map):
        async def fake_discover(client, addr):
            wallet._TOKEN_SET_CACHE.setdefault(
                addr.lower(), {"contracts": dict(CONTRACTS), "newest_block": 1, "discovered_ts": 9e18})
            return dict(CONTRACTS)

        async def fake_native(client, path, params=None, full=False):
            return {"balance": _raw(1000)}

        async def fake_v2(client, params):
            if params.get("action") == "tokenbalance":
                return {"0xxyo": _raw(120000), "0xada": _raw(40)}.get(params.get("contractaddress"))
            return []

        async def fake_prices(client, contracts):
            return dict(price_map)

        with mock.patch.object(wallet, "_discover_token_set", side_effect=fake_discover), \
             mock.patch.object(wallet, "explorer_get", side_effect=fake_native), \
             mock.patch.object(wallet, "_v2_get", side_effect=fake_v2), \
             mock.patch.object(wallet, "get_token_prices", side_effect=fake_prices), \
             mock.patch.object(wallet, "check_data_freshness", new=mock.AsyncMock()):
            return _run(wallet.get_wallet_balances(W))

    def test_total_stable_when_one_price_lookup_fails(self):
        os.environ["WALLET_BALANCE_REFRESH_HOURS"] = "6"
        wallet.WALLET_PRICE_MAX_STALE_HOURS = 24.0
        # cycle 1: everything priced
        r1 = self._call({"0xxyo": 0.0004, "0xada": 0.4, WCRO: 0.08})
        t1 = r1["usd_total"]
        xyo1 = next(d for d in r1["token_details"] if d["symbol"] == "XYO")
        self.assertAlmostEqual(xyo1["usd"], 48.0)         # 120000 * 0.0004
        self.assertFalse(xyo1.get("price_stale"))

        # cycle 2: XYO price MISSING -> carried from cache, still counted
        r2 = self._call({"0xada": 0.4, WCRO: 0.08})
        t2 = r2["usd_total"]
        xyo2 = next(d for d in r2["token_details"] if d["symbol"] == "XYO")
        self.assertAlmostEqual(xyo2["usd"], 48.0)         # last-known price kept
        self.assertTrue(xyo2["price_stale"])              # marked stale
        self.assertAlmostEqual(t1, t2)                    # total DID NOT swing
        self.assertGreaterEqual(r2["price_stale_count"], 1)

    def test_expiry_drops_to_unknown_and_excludes_from_total(self):
        os.environ["WALLET_BALANCE_REFRESH_HOURS"] = "6"
        self._call({"0xxyo": 0.0004, "0xada": 0.4, WCRO: 0.08})  # seed cache
        wallet.WALLET_PRICE_MAX_STALE_HOURS = 0.0                  # everything cached is expired
        r2 = self._call({"0xada": 0.4, WCRO: 0.08})               # XYO missing + cache expired
        xyo = next(d for d in r2["token_details"] if d["symbol"] == "XYO")
        self.assertIsNone(xyo["usd"])                             # genuinely price unknown now
        self.assertFalse(xyo["price_stale"])
        # total excludes XYO (only ADA priced): 40*0.4 + cro
        self.assertNotIn(48.0, [d.get("usd") for d in r2["token_details"]])
        wallet.WALLET_PRICE_MAX_STALE_HOURS = 24.0

    def test_never_priced_token_shows_unknown_not_stale(self):
        os.environ["WALLET_BALANCE_REFRESH_HOURS"] = "6"
        wallet.WALLET_PRICE_MAX_STALE_HOURS = 24.0
        r = self._call({"0xada": 0.4, WCRO: 0.08})  # XYO never had a price
        xyo = next(d for d in r["token_details"] if d["symbol"] == "XYO")
        self.assertIsNone(xyo["usd"])
        self.assertFalse(xyo["price_stale"])


class TestFooter(unittest.TestCase):
    def test_footer_reports_stale_count_and_age(self):
        from app.commands.balances import _render_usd
        bal = {"cro": 1000.0, "cro_usd": 81.0, "usd_total": 129.0,
               "tokens": {"XYO": 120000.0, "ADA": 40.0},
               "token_details": [
                   {"symbol": "XYO", "contract": "0xa", "amount": 120000.0, "usd": 48.0,
                    "stale": False, "price_stale": True, "price_age_h": 3.2},
                   {"symbol": "ADA", "contract": "0xb", "amount": 40.0, "usd": 16.0,
                    "stale": False, "price_stale": False}],
               "priced": True, "ok": True,
               "price_stale_count": 1, "price_stale_oldest_h": 3.2}
        out = _render_usd(W, bal)
        self.assertIn("last-known prices", out)
        self.assertIn("3.2h", out)
        xyo_line = [l for l in out.splitlines() if "XYO" in l][0]
        self.assertIn("last known", xyo_line)


if __name__ == "__main__":
    unittest.main()
