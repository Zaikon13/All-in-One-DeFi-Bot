# /paper command + mirror endpoint (2026-07-17). Offline — no network.

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token-123")

from app.commands.paper import render_paper_status

NOW = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)


def _mirror(state=None, as_of=None):
    return {"state": state, "as_of": (as_of or NOW).isoformat()}


def _state():
    return {
        "balance_usd": 955.0, "starting_usd": 1000.0,
        "open": [{"symbol": "WOOF/WCRO", "pair_address": "0xp", "token_address": "0xt",
                  "entry_price": 0.002, "qty": 25000.0, "usd_in": 50.0,
                  "score": 72.4, "opened_at": NOW.isoformat()}],
        "closed": [
            {"symbol": "MOON/WCRO", "pnl_usd": 12.5, "pnl_pct": 25.0, "exit_reason": "take-profit"},
            {"symbol": "DUST/WCRO", "pnl_usd": -7.5, "pnl_pct": -15.0, "exit_reason": "stop-loss"},
        ],
    }


class TestRenderPaperStatus(unittest.TestCase):
    def test_no_mirror_says_syncing(self):
        out = render_paper_status(None, now_utc=NOW)
        self.assertIn("syncing", out.lower())
        self.assertIn("🧪", out)

    def test_full_render_with_prices(self):
        out = render_paper_status(_mirror(_state()), {"0xt": 0.0022}, now_utc=NOW)
        self.assertIn("simulation only", out)
        self.assertIn("(started $1,000, realized +5.00)", out)  # exact header; 12.5-7.5=+5, equity-consistent
        self.assertIn("WOOF/WCRO", out)
        self.assertIn("unrealized +5.00 USD (+10.0%)", out)  # 25000*0.0022-50
        self.assertIn("✅ **MOON/WCRO** +12.50 USD (+25.0%) · take-profit", out)
        self.assertIn("❌ **DUST/WCRO** -7.50 USD (-15.0%) · stop-loss", out)
        self.assertIn("**Win rate:** 50%", out)
        self.assertNotIn("```", out)

    def test_missing_price_says_unknown_never_exits_claims(self):
        out = render_paper_status(_mirror(_state()), {}, now_utc=NOW)
        self.assertIn("current price unknown", out)

    def test_stale_mirror_warns(self):
        out = render_paper_status(_mirror(_state(), as_of=NOW - timedelta(minutes=45)),
                                  {}, now_utc=NOW)
        self.assertIn("45 min old", out)

    def test_empty_state_encourages_patience(self):
        st = {"balance_usd": 1000.0, "starting_usd": 1000.0, "open": [], "closed": []}
        out = render_paper_status(_mirror(st), now_utc=NOW)
        self.assertIn("patience IS the strategy", out)
        self.assertIn("**Win rate:** —", out)


class TestMirrorEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        import app.main as main
        cls.main = main
        cls.client = TestClient(main.app)
        cls.auth = main._paper_mirror_auth()

    def test_wrong_auth_rejected(self):
        r = self.client.post("/internal/paper-state", json={"state": {}},
                             headers={"X-Paper-Auth": "wrong"})
        self.assertEqual(r.status_code, 403)
        r = self.client.post("/internal/paper-state", json={"state": {}})
        self.assertEqual(r.status_code, 403)

    def test_valid_push_lands_in_mirror(self):
        st = {"balance_usd": 950.0, "starting_usd": 1000.0, "open": [], "closed": []}
        r = self.client.post("/internal/paper-state",
                             json={"state": st, "as_of": NOW.isoformat()},
                             headers={"X-Paper-Auth": self.auth})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.main.get_paper_mirror()["state"]["balance_usd"], 950.0)

    def test_garbage_payload_rejected(self):
        r = self.client.post("/internal/paper-state", content=b"not json",
                             headers={"X-Paper-Auth": self.auth,
                                      "Content-Type": "application/json"})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
