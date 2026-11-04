# Critical-function registry (docs/CRITICAL_FUNCTIONS.md) — offline, static.
# 1) every registered critical function must still exist (a rename can't silently orphan it);
# 2) coverage ratchet: every critical function must be referenced by at least one test file,
#    except the KNOWN_GAPS below — and a gap that gets covered must be removed from the list.

import importlib
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")

CRITICAL = [  # (module, function) — mirrors docs/CRITICAL_FUNCTIONS.md
    # Tier 1 — delivery & routing
    ("app.main", "send_telegram_message"), ("app.main", "handle_command"),
    ("app.main", "telegram_webhook"), ("worker", "send_telegram"),
    ("core.wallet", "send_telegram_alert"), ("core.tg_format", "to_tg_markdown"),
    ("core.tg_format", "split_message"), ("core.tg_format", "plain_text"),
    ("run_local", "_telegram_poll_loop"), ("core.telegram_webhook", "ensure_webhook"),
    ("core.local_mode", "configured_allowed_chats"),
    # Tier 2 — money numbers
    ("core.wallet", "get_wallet_balances"), ("core.wallet", "_discover_token_set"),
    ("core.wallet", "parse_raw_balance"), ("core.wallet", "explorer_get"),
    ("core.wallet", "_v2_get"), ("core.wallet", "get_token_prices"),
    ("core.wallet", "check_data_freshness"),
    ("core.pnl_calculator", "get_today_transactions_async"),
    ("core.pnl_calculator", "_aggregate_pnl"), ("core.pnl_calculator", "get_daily_pnl_report"),
    # Tier 3 — scanner & simulation
    ("worker", "poll_new_pools"), ("worker", "score_pair"), ("worker", "_paper_step"),
    ("core.pair_discovery", "fetch_new_pools"), ("core.pair_discovery", "fetch_pool_prices"),
    ("core.pair_discovery", "parse_gt_pool"), ("core.pair_discovery", "classify_pool"),
    ("core.paper_trading", "check_exit"), ("core.paper_trading", "close_position"),
    ("core.paper_trading", "load_state"), ("core.paper_trading", "repair_impossible_trades"),
    ("core.paper_trading", "reconcile_balance"),
    # Tier 4 — runtime
    ("worker", "main"), ("worker", "scheduled_eod_pnl"), ("worker", "scheduled_scan_digest"),
    ("worker", "seconds_until_local"),
    ("worker", "portfolio_watch"), ("worker", "detect_portfolio_moves"),
    ("run_local", "_amain"), ("core.claude_client", "call_claude"),
]

# Critical functions with NO test yet (2026-11-04). The Test Guardian closes these; when one
# gets covered, remove it here (test_known_gaps_are_still_gaps enforces that).
KNOWN_GAPS = {
    "_aggregate_pnl", "fetch_new_pools", "fetch_pool_prices", "_paper_step",
    "scheduled_eod_pnl", "scheduled_scan_digest", "portfolio_watch", "call_claude",
    "main",  # worker.main (the gather of all loops)
}

THIS = os.path.basename(__file__)


def _test_sources():
    tdir = os.path.join(ROOT, "tests")
    out = {}
    for f in os.listdir(tdir):
        if f.endswith(".py") and f != THIS:
            out[f] = open(os.path.join(tdir, f), encoding="utf-8").read()
    return out


# names too generic to count as a reference on their own (unittest.main() etc.)
GENERIC = {"main"}


def _referenced(name, sources, module=None):
    if name in GENERIC and module:
        name = module.split(".")[-1] + "." + name  # require e.g. "worker.main"
    pat = re.compile(r"(?<![\w])" + re.escape(name) + r"(?![\w])")
    for src in sources.values():
        for m in pat.finditer(src):
            line = src[src.rfind("\n", 0, m.start()) + 1: src.find("\n", m.start())]
            if not re.match(r"\s*(async\s+)?def\s", line) and not line.lstrip().startswith("#"):
                return True
    return False


class TestCriticalRegistry(unittest.TestCase):
    def test_every_critical_function_exists(self):
        for mod, n in CRITICAL:
            m = importlib.import_module(mod)
            self.assertTrue(callable(getattr(m, n, None)), f"{mod}.{n} is gone — update the registry")

    def test_every_critical_function_is_tested(self):
        sources = _test_sources()
        untested = sorted(n for mod, n in CRITICAL if n not in KNOWN_GAPS and not _referenced(n, sources, mod))
        self.assertEqual(untested, [], "critical functions with no test (add one, or list in KNOWN_GAPS with a reason)")

    def test_known_gaps_are_still_gaps(self):
        sources = _test_sources()
        mods = {n: mod for mod, n in CRITICAL}
        closed = sorted(n for n in KNOWN_GAPS if _referenced(n, sources, mods.get(n)))
        self.assertEqual(closed, [], "these gaps are now covered — remove them from KNOWN_GAPS")

    def test_registry_doc_lists_every_function(self):
        doc = open(os.path.join(ROOT, "docs", "CRITICAL_FUNCTIONS.md"), encoding="utf-8").read()
        missing = sorted(n for _, n in CRITICAL if f"`{n}`" not in doc and f" {n}`" not in doc)
        self.assertEqual(missing, [], "keep docs/CRITICAL_FUNCTIONS.md in sync with this registry")


if __name__ == "__main__":
    unittest.main()
