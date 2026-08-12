"""Compact /paper mirror payload (2026-08-11).

The worker POSTs its paper state to the bot's /internal/paper-state so /paper can
render it. It used to send the WHOLE state — including the full closed[] history,
which grows without bound. Once it passed the bot's 200 KB body cap
(app/main.py) every push returned 413 and /paper went stale. compact_paper_state
sends only what /paper renders (balance, starting, open positions, total count,
wins, last ~10 closed), so the payload stays small no matter how long the history
gets. These tests pin the size guarantee and that the renderer still shows real
totals from the compact shape.
"""
import json
from datetime import datetime, timezone

import core.paper_trading as pt
from app.commands.paper import render_paper_status

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
BOT_BODY_CAP = 200_000  # must match the limit in app/main.py /internal/paper-state


def _state(n_closed, n_open=5):
    st = pt.fresh_state()
    st["balance_usd"] = 1068.56
    st["starting_usd"] = 1000.0
    st["open"] = [{"chain": "solana", "pair_address": f"pool{i}", "token_address": f"tok{i}",
                   "symbol": f"OPEN{i}/SOL", "entry_price": 0.01, "qty": 5000.0, "usd_in": 50.0,
                   "score": 80.0, "opened_at": NOW.isoformat(),
                   "flags": {"suspicious": False, "implausible_liq": False}}
                  for i in range(n_open)]
    # full-size closed records, incl. the repair audit fields that bloated the payload
    st["closed"] = [{"chain": "solana", "pair_address": f"cp{i}", "token_address": f"ct{i}",
                     "symbol": f"TKN{i}/SOL", "entry_price": 0.002, "qty": 25000.0, "usd_in": 50.0,
                     "score": 75.0, "opened_at": NOW.isoformat(),
                     "flags": {"suspicious": False, "implausible_liq": False},
                     "exit_price": 0.0025, "exit_reason": "take-profit", "closed_at": NOW.isoformat(),
                     "pnl_usd": 12.5 if i % 3 else -7.5, "pnl_pct": 25.0 if i % 3 else -15.0,
                     "original_pnl_usd": 21568.52, "original_pnl_pct": 43137.0,
                     "original_exit_price": 0.863,
                     "corrected": "capped to +25% TP (was an impossible glitch tick)"}
                    for i in range(n_closed)]
    return st


def _signals():
    chains = ["cro", "solana", "sui-network"]
    return {"chains": chains,
            "thresholds": {c: {"min_liq": 10000, "min_score": 35} for c in chains},
            "funnel": {c: {"seen": 420, "matured": 300, "passed": 2, "sent": 2, "best": 71} for c in chains},
            "recent": [{"chain": "solana", "symbol": f"S{i}", "quote": "SOL", "dex": "raydium",
                        "score": 71, "tier": "🔥", "age_h": 0.5, "liquidity": 50000, "vol1h": 30000,
                        "buys": 40, "sells": 5, "suspicious": False, "implausible_liq": False,
                        "ts": NOW.isoformat()} for i in range(40)]}


class TestPayloadSize:
    def test_full_state_would_exceed_the_cap(self):
        # this is the bug: the old full-state payload blows past 200 KB
        full = json.dumps({"state": _state(1000), "signals": _signals(), "as_of": NOW.isoformat()})
        assert len(full) > BOT_BODY_CAP

    def test_compact_payload_stays_under_cap_with_huge_history(self):
        payload = json.dumps({"state": pt.compact_paper_state(_state(50000)),
                              "signals": _signals(), "as_of": NOW.isoformat()})
        assert len(payload) < BOT_BODY_CAP
        assert len(payload) < 20_000  # genuinely small, not just barely under

    def test_compact_size_is_bounded_regardless_of_history_length(self):
        # 5,000x more history must NOT grow the payload
        sizes = [len(json.dumps(pt.compact_paper_state(_state(n)))) for n in (10, 1000, 50000)]
        assert all(s < 6000 for s in sizes), sizes
        assert max(sizes) - min(sizes) < 100  # only the count/wins integers differ

    def test_compact_omits_the_unbounded_list(self):
        c = pt.compact_paper_state(_state(1000))
        assert "closed" not in c              # never ship the full history
        assert c["closed_count"] == 1000      # ...but keep the true total
        assert len(c["closed_recent"]) == 10  # only the display tail
        assert len(c["open"]) == 5


class TestRenderFromCompact:
    def test_renders_real_totals_from_compact_mirror(self):
        compact = pt.compact_paper_state(_state(351))
        out = render_paper_status({"state": compact, "as_of": NOW.isoformat()}, prices={}, now_utc=NOW)
        assert "351 total" in out                 # true count, not the 10 we shipped
        assert "$1,068.56" in out                 # the repaired balance
        assert "realized +318.56" in out          # 1068.56 + 250 open basis - 1000
        # win rate computed from wins/closed_count (234 wins / 351 = 67%)
        assert "**Win rate:** 67%" in out
        assert out.count(" USD (") == 10          # last 10 closed rendered

    def test_backward_compatible_with_a_full_state(self):
        out = render_paper_status({"state": _state(12), "as_of": NOW.isoformat()}, prices={}, now_utc=NOW)
        assert "12 total" in out

    def test_syncing_message_when_no_mirror(self):
        assert "syncing" in render_paper_status(None, now_utc=NOW)
