# Critical-function tests (docs/CRITICAL_FUNCTIONS.md, Tier 2):
#   core/pnl_calculator.py `_aggregate_pnl` — daily report math.
#   Invariant: net = in − out per token; failed transactions skipped.
# Offline + pure. Rows go through the SAME adapter chain production uses
# (_adapt_explorer_row -> _normalize_etherscan_item -> _aggregate_pnl).

import importlib
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pnl = None  # core.pnl_calculator, bound lazily in _PnlCase.setUp

W = "0x1234567890abcdef1234567890abcdef12345678"     # the monitored wallet
OTHER = "0x9999999999999999999999999999999999999999"


def _row(frm, to, raw_value, symbol=None, decimals=None, error=None, ts=1_793_000_000):
    """A Cronos Explorer v1 row (nested from/to; token meta in tokenMetadata)."""
    r = {"from": {"address": frm, "isContract": False}, "to": {"address": to, "isContract": False},
         "value": str(raw_value), "timestamp": ts, "transactionHash": "0xabc", "error": error}
    if symbol is not None:
        r["tokenMetadata"] = {"tokenSymbol": symbol, "decimals": decimals}
    return r


def _tx(row, action):
    """Production adaptation path for one Explorer row."""
    return pnl._normalize_etherscan_item(pnl._adapt_explorer_row(row, action), action)


def _by_symbol(result):
    return {t["symbol"]: t for t in result["tokens"]}


class _PnlCase(unittest.TestCase):
    """Imports core.pnl_calculator lazily. test_pnl_honesty / test_phase1_enrichment
    set WALLET_ADDRESS before their FIRST import of it (it is read at import time),
    so this file must never be that first importer during pytest collection."""

    def setUp(self):
        global pnl
        pnl = importlib.import_module("core.pnl_calculator")
        p = mock.patch.object(pnl, "WALLET_ADDRESS", W)
        p.start()
        self.addCleanup(p.stop)


class TestAggregatePnlNetFlow(_PnlCase):

    def test_net_is_in_minus_out_per_token(self):
        """Invariant: net = in − out per token (each token aggregated on its own).
        Mutation that breaks it: `net = buys + sells` (or swapping the delta sign)."""
        txs = [
            _tx(_row(OTHER, W, 100_000_000, "USDC", 6), "tokentx"),   # +100 USDC
            _tx(_row(OTHER, W, 50_000_000, "USDC", 6), "tokentx"),    # +50 USDC
            _tx(_row(W, OTHER, 30_000_000, "USDC", 6), "tokentx"),    # -30 USDC
            _tx(_row(OTHER, W, 5 * 10**18), "txlist"),                # +5 CRO (native)
            _tx(_row(W, OTHER, 2 * 10**18), "txlist"),                # -2 CRO (native)
        ]
        toks = _by_symbol(pnl._aggregate_pnl(txs))
        self.assertAlmostEqual(toks["USDC"]["net"], 120.0)
        self.assertEqual(toks["USDC"]["trades"], 3)
        self.assertAlmostEqual(toks["CRO"]["net"], 3.0)
        self.assertEqual(toks["CRO"]["trades"], 2)

    def test_pure_outflow_is_negative(self):
        """Invariant: net = in − out — an outflow-only day is negative, never abs()'d.
        Mutation that breaks it: storing abs(net)."""
        toks = _by_symbol(pnl._aggregate_pnl([_tx(_row(W, OTHER, 7_500_000, "USDC", 6), "tokentx")]))
        self.assertAlmostEqual(toks["USDC"]["net"], -7.5)

    def test_native_cro_is_not_double_counted(self):
        """Invariant: net = in − out. A normalized native-CRO row carries BOTH a
        transfers[] delta and a top-level `value`; it must count once (+5, not +10).
        Mutation that breaks it: dropping the `"CRO" in symbols_with_transfer_delta` guard."""
        tx = _tx(_row(OTHER, W, 5 * 10**18), "txlist")
        self.assertEqual(tx["value"], str(5 * 10**18))            # precondition: both present
        self.assertTrue(tx["transfers"])
        toks = _by_symbol(pnl._aggregate_pnl([tx]))
        self.assertAlmostEqual(toks["CRO"]["net"], 5.0)
        self.assertEqual(toks["CRO"]["trades"], 1)

    def test_native_value_only_tx_is_signed_by_direction(self):
        """Invariant: net = in − out for native CRO carried only in tx `value`
        (no transfers[]): sent from the wallet → negative. Mutation that breaks
        it: `tx_type = "BUY"` unconditionally."""
        tx = {"successful": True, "from_address": W, "to_address": OTHER,
              "value": str(2 * 10**18), "transfers": [], "log_events": [],
              "block_signed_at": "2026-11-04T10:00:00Z"}
        toks = _by_symbol(pnl._aggregate_pnl([tx]))
        self.assertAlmostEqual(toks["CRO"]["net"], -2.0)

    def test_log_event_does_not_double_count_a_transfer(self):
        """Invariant: net = in − out — a Transfer log_event for a symbol already
        moved by transfers[] in the same tx is ignored (dedup guardrail)."""
        tx = {"successful": True, "from_address": OTHER, "to_address": W, "value": "0",
              "block_signed_at": "2026-11-04T10:00:00Z",
              "transfers": [{"contract_ticker_symbol": "USDC", "contract_decimals": 6, "delta": 100_000_000}],
              "log_events": [{"sender_contract_ticker_symbol": "USDC", "sender_contract_decimals": 6,
                              "decoded": {"name": "Transfer", "params": [
                                  {"name": "from", "value": OTHER}, {"name": "to", "value": W},
                                  {"name": "value", "value": "100000000"}]}}]}
        toks = _by_symbol(pnl._aggregate_pnl([tx]))
        self.assertAlmostEqual(toks["USDC"]["net"], 100.0)
        self.assertEqual(toks["USDC"]["trades"], 1)

    def test_empty_input_is_an_error_not_a_zero_day(self):
        """Invariant support: no transactions → the error shape the report layer
        turns into 'No meaningful transactions', never a fabricated token list."""
        self.assertIn("error", pnl._aggregate_pnl([]))

    @unittest.expectedFailure
    def test_self_transfer_nets_to_zero(self):
        """Invariant: net = in − out per token. A self-transfer (from == to == the
        wallet) moves X in AND X out, so net must be 0.
        BUG (finding): _normalize_etherscan_item signs the delta with
        `raw if to == wallet else -raw`, so a self-transfer is booked as a pure
        +X inflow and the daily report shows +100 USDC that never arrived."""
        toks = _by_symbol(pnl._aggregate_pnl([_tx(_row(W, W, 100_000_000, "USDC", 6), "tokentx")]))
        self.assertAlmostEqual(toks.get("USDC", {"net": 0.0})["net"], 0.0)


class TestAggregatePnlSkipsFailedTransactions(_PnlCase):

    def test_failed_token_transfer_is_skipped(self):
        """Invariant: failed transactions skipped. A reverted 1000-USDC inflow must
        not count; only the successful +10 does. Mutation that breaks it: removing
        `if not tx.get("successful", True): continue`."""
        txs = [
            _tx(_row(OTHER, W, 1_000_000_000, "USDC", 6, error="execution reverted"), "tokentx"),
            _tx(_row(OTHER, W, 10_000_000, "USDC", 6), "tokentx"),
        ]
        self.assertFalse(txs[0]["successful"])                     # precondition: adapter marks it
        toks = _by_symbol(pnl._aggregate_pnl(txs))
        self.assertAlmostEqual(toks["USDC"]["net"], 10.0)
        self.assertEqual(toks["USDC"]["trades"], 1)

    def test_failed_native_transfer_is_skipped(self):
        """Invariant: failed transactions skipped — a reverted native send leaves
        no CRO entry at all (neither the transfer delta nor the `value` path)."""
        res = pnl._aggregate_pnl([_tx(_row(W, OTHER, 9 * 10**18, error="out of gas"), "txlist")])
        self.assertNotIn("CRO", _by_symbol(res))

    def test_unsuccessful_flag_skips_every_path(self):
        """Invariant: failed transactions skipped — even when the tx also carries
        a native `value` and a Transfer log_event."""
        tx = {"successful": False, "from_address": OTHER, "to_address": W,
              "value": str(3 * 10**18), "block_signed_at": "2026-11-04T10:00:00Z",
              "transfers": [{"contract_ticker_symbol": "USDC", "contract_decimals": 6, "delta": 5_000_000}],
              "log_events": [{"sender_contract_ticker_symbol": "WOOF", "sender_contract_decimals": 18,
                              "decoded": {"name": "Transfer", "params": [
                                  {"name": "from", "value": OTHER}, {"name": "to", "value": W},
                                  {"name": "value", "value": str(10**18)}]}}]}
        self.assertEqual(pnl._aggregate_pnl([tx])["tokens"], [])


if __name__ == "__main__":
    unittest.main()
