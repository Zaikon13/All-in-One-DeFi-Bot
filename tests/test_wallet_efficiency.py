# Part C (2026-07-13): balance reads are cut to the "held set" each cycle with a
# periodic full sweep. Offline unit tests for the pure selection/update helpers.

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.wallet import _select_balance_contracts, _update_held

REFRESH = 6 * 3600  # seconds
DUST = 0.0001


class TestSelectBalanceContracts(unittest.TestCase):
    def test_cold_cache_is_full_sweep_of_all_candidates(self):
        cands = {"0xa": (), "0xb": (), "0xc": ()}
        to_check, is_full = _select_balance_contracts(cands, {}, now=1000.0, refresh_seconds=REFRESH)
        self.assertTrue(is_full)
        self.assertEqual(set(to_check), {"0xa", "0xb", "0xc"})

    def test_expired_full_sweep_refreshes_everything(self):
        entry = {"held_set": {"0xa"}, "last_full_ts": 0.0,
                 "balance_seen": {"0xa", "0xb", "0xc"}}
        cands = {"0xa": (), "0xb": (), "0xc": ()}
        to_check, is_full = _select_balance_contracts(cands, entry, now=REFRESH + 1, refresh_seconds=REFRESH)
        self.assertTrue(is_full)
        self.assertEqual(set(to_check), {"0xa", "0xb", "0xc"})

    def test_recent_cache_is_incremental_held_plus_unseen(self):
        # held = {0xa}; already balance-checked {0xa,0xb}; 0xc is a new candidate
        entry = {"held_set": {"0xa"}, "last_full_ts": 100.0,
                 "balance_seen": {"0xa", "0xb"}}
        cands = {"0xa": (), "0xb": (), "0xc": ()}
        to_check, is_full = _select_balance_contracts(cands, entry, now=200.0, refresh_seconds=REFRESH)
        self.assertFalse(is_full)
        # held (0xa) + never-seen candidate (0xc); the zero token 0xb is skipped
        self.assertEqual(set(to_check), {"0xa", "0xc"})

    def test_incremental_read_count_is_small_vs_candidates(self):
        # 200 historical candidates but only 5 held -> incremental reads ~5, not 200
        cands = {f"0x{i:040x}": () for i in range(200)}
        held = {f"0x{i:040x}" for i in range(5)}
        entry = {"held_set": set(held), "last_full_ts": 100.0, "balance_seen": set(cands)}
        to_check, is_full = _select_balance_contracts(cands, entry, now=200.0, refresh_seconds=REFRESH)
        self.assertFalse(is_full)
        self.assertEqual(set(to_check), held)
        self.assertLess(len(to_check), 10)


class TestUpdateHeld(unittest.TestCase):
    def test_full_sweep_recomputes_held_and_stamps_time(self):
        entry = {}
        _update_held(entry, ["0xa", "0xb", "0xc"],
                     {"0xa": 5.0, "0xb": 0.0, "0xc": 100.0}, DUST, is_full=True, now=999.0)
        self.assertEqual(entry["held_set"], {"0xa", "0xc"})
        self.assertEqual(entry["last_full_ts"], 999.0)
        self.assertEqual(entry["balance_seen"], {"0xa", "0xb", "0xc"})

    def test_incremental_drops_sold_token_keeps_others(self):
        # held {0xa,0xc}; this cycle re-checks both, 0xa sold to 0
        entry = {"held_set": {"0xa", "0xc"}, "last_full_ts": 100.0, "balance_seen": {"0xa", "0xc"}}
        _update_held(entry, ["0xa", "0xc"], {"0xa": 0.0, "0xc": 50.0}, DUST, is_full=False, now=200.0)
        self.assertEqual(entry["held_set"], {"0xc"})
        self.assertEqual(entry["last_full_ts"], 100.0)  # unchanged on incremental

    def test_incremental_adds_newly_received_token(self):
        entry = {"held_set": {"0xa"}, "last_full_ts": 100.0, "balance_seen": {"0xa"}}
        _update_held(entry, ["0xa", "0xnew"], {"0xa": 5.0, "0xnew": 12.0}, DUST, is_full=False, now=200.0)
        self.assertEqual(entry["held_set"], {"0xa", "0xnew"})
        self.assertIn("0xnew", entry["balance_seen"])


if __name__ == "__main__":
    unittest.main()
