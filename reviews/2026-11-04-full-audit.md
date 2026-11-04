# Full audit — 2026-11-04

Scope: every production file (`worker.py`, `app/`, `core/`), CI workflows, deploy config and docs,
read line by line against the live code. Fixed items have tests in `tests/test_audit_fixes.py`
and `tests/test_local_mode.py` (suite: 219 passed, 2 skipped).

Limit of this audit: the cloud session's network policy blocks GeckoTerminal, Dexscreener, the
Cronos Explorer/RPC and Telegram. So the fixes below are verified offline (mocked I/O). They are
**not** verified against live data, and that is the next step.

## Why the bot looked dead

1. **The bot has been down since at least 2026-08-22.** From then until 2026-10-11 the
   health-check workflow opened 191 open duplicate issues "Health check: /health returned 404",
   one every ~6 h, and each run also called the Claude API.
2. **`/start` never arrived.** The reply keyboard was a flat list, which Telegram rejects (400). The
   menu text also contained a bare `_` (`/daily_pnl`), which Telegram's legacy Markdown reads as
   an unclosed italic, so that was a second 400. The bot sender had no fallback, so the reply was lost.
3. **Any reply with an odd `_`/`*`, or longer than 4096 chars, was lost the same way.** The
   worker already retried as plain text. The bot did not, so long `/daily_pnl` reports simply
   never arrived.
4. **The chat was flooded.** An hourly heartbeat sent 24 messages a day, on top of per-cycle pool
   alerts.

## Fixed in this change

| # | Problem | Where | Fix |
|---|---------|-------|-----|
| 1 | `/start` keyboard malformed + bare `_` → menu never delivered | `app/main.py` | rows-of-buttons keyboard; `/daily\_pnl` escaped |
| 2 | `**bold**` is an *empty* span in Telegram legacy Markdown, so nothing was ever bold | all senders | `core/tg_format.to_tg_markdown` at the send boundary |
| 3 | Bot replies lost on any Markdown 400 | `app/main.py` | plain-text retry (markers stripped, escapes undone) |
| 4 | Replies > 4096 chars rejected | bot + worker senders | `split_message` on line boundaries |
| 5 | `tokenbalance` error text (HTTP 200 + status 0, e.g. "Max rate limit reached") parsed as a *confirmed 0* → a real holding was deleted from /wallet | `core/wallet.py` | `parse_raw_balance`: non-numeric = failed read, keep last known |
| 6 | A failed `tokentx` page counted as "end of history", so the cold discovery was cached incomplete forever and those tokens were never shown | `core/wallet.py` | failure ≠ empty; incomplete walks re-run after 15 min; partial results kept |
| 7 | `/paper` priced open positions via a Cronos-only lookup with lowercased addresses → every Solana/Sui position "price unknown" | `worker.py`, `core/paper_trading.py`, `app/commands/paper.py` | worker stores its own last observed pool price per position; `/paper` falls back to it with its age |
| 8 | Daily report "Avg Cost" = today's buys valued at today's price ÷ same qty, so always the current price (fake metric) | `core/pnl_calculator.py` | removed |
| 9 | "Total Portfolio Value" was really the USD value of the day's *net flow*, and hidden on outflow days | same | relabeled "Net flow today", negative values shown |
| 10 | Report titled "Daily PnL" but it is net token in − out, not P&L | same | title + one-line note say what it measures |
| 11 | CoinGecko lookup synchronous (`httpx.Client` + `time.sleep`) inside async code → froze the event loop | same | runs in `asyncio.to_thread` |
| 12 | CoinGecko id guessed as `symbol.lower()` → could price an unrelated coin; mixed-case symbols never matched | `core/price_service.py`, `core/pnl_calculator.py` | known ids only; case-insensitive lookup |
| 13 | Hourly heartbeat spam (local time, no TZ) | `worker.py` | opt-in `HEARTBEAT_ENABLED` (default off) |
| 14 | EOD default hour 0 reported the just-started empty day; feature off by default | `worker.py` | default ON with a wallet, at 23:55 Athens; 22 h dup guard (DST-safe) |
| 15 | Health-check workflow: issue every 6 h + paid Claude call against a down service | `.github/workflows/claude-health-check.yml` | schedule removed (manual only); at most one open issue |
| 16 | Sync-check ran daily for nothing (a fresh checkout is always in sync) | `sync-check.yml` | daily schedule removed |
| 17 | Dead `telegram/` package shadowed the pip `telegram` package; `python-telegram-bot` and `schedule` unused | repo root, `requirements.txt` | deleted / dropped |
| 18 | Orphaned `app/health.py`, `app/github_webhook.py` (the latter accepted unsigned requests if ever mounted) | `app/` | deleted |
| 19 | User-facing text still said "Grok" on a Claude bot | `app/main.py`, `core/pnl_calculator.py` | "AI" |
| 20 | Dead `WEBHOOK_BASE_URL` default pointing at the deleted `web-gpl6` | `app/main.py` | removed |
| 21 | CLAUDE.md golden rule taught the wrong bold syntax; listed 3 Railway services incl. the deleted one | `CLAUDE.md` | corrected |

Earlier in the same PR (#224): standalone `run_local.py` (no Railway), the shared command router,
fail-closed chat allow-list, "feed unavailable" honesty in `/signals`, and the CodeQL fix.

## Not fixed (needs the owner, or a decision)

- **Security:** a real-looking `ETHERSCAN_API_KEY` is in *public* git history (`.env.example`,
  commits cc23605 / 9acdbd3). The live code no longer uses it, but it must be revoked at
  Etherscan.
- **191 open spam issues** (#33 to #223): these can be bulk-closed. This was not done without the owner's OK.
- **Daily "PnL" is still not P&L.** Real P&L needs historical prices and a cost basis per
  token. That is a feature to build, not a bug fix.
- **Paper-trading evidence:** after the August repair, the projected result of the 🔥-tier
  strategy was roughly break-even. That is no evidence of an edge yet. The state lived on the
  Railway volume, which is unreachable while Railway is paused.
- **Unverified API semantics:** the v1 `getTxsByAddress` sort order and the v2 rate-limit
  response shape were inferred from code comments. They need checking against the live API.
- **Dependencies are unpinned** (`fastapi`, `httpx`, `anthropic`, …). A future major release
  can break a fresh install.
- **Code noise:** hundreds of lines of "Review Agent …" process comments. Some are even inside
  runtime log text (`worker._warn_if_no_volume`).

## Costs

- The repo is **public**, so GitHub Actions and CodeQL are free. Nothing here needs GitHub Pro.
- Railway: everything can run as **one** service (`python -u run_local.py`) instead of two.
  It does not need a public URL or a separate web service.
