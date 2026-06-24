# CLAUDE.md

Project memory for Claude Code. Read this fully before doing anything in this repo.

---

## ⚠️ Read this first: the docs lie

The markdown "source of truth" files in this repo (`GROK_USAGE.md`, `GROK_COORDINATION.md`,
`AGENTS.md`, `project-awareness.md`, `docs/project-status.md`, `SUMMARY.md`, `GROK_HEALTH.md`)
were written during the Grok era and are **stale**. They describe Grok as the bot's brain and
`core/grok_client.py` as the source of truth. **That is no longer true.** Always verify claims
against the actual code. When docs and code disagree, the code wins — and fix the doc.

---

## What this project is

**All-in-One-DeFi-Bot** — a Python / FastAPI Telegram bot that monitors a Cronos wallet and
reports balances, daily PnL, and new Dexscreener pairs. Deployed on Railway via Docker.

- **It monitors and reports only. It does NOT execute trades.** (Trading is a future goal, not built.)
- Repo: https://github.com/Zaikon13/All-in-One-DeFi-Bot

## Architecture

- **Web service** — `app/main.py` (FastAPI + uvicorn). Telegram webhook at `/telegram/webhook`,
  wallet analysis at `/grok/analyze`, daily PnL, health at `/` and `/health`.
- **Worker** — `worker.py`. Polls Dexscreener for new Cronos pairs, monitors the wallet, sends a
  heartbeat, runs end-of-day PnL. Persists state to a Railway volume at `/data`.
- **core/** — shared helpers. `claude_client.py` (AI calls), `wallet.py`, `pnl_calculator.py`,
  `price_service.py`, Dexscreener access. **Reuse these; do not duplicate their logic in `app/` or `worker/`.**
- **Blockchain data source (2026-06-21, balances rev. 2026-06-24).** Live, keyed Cronos Explorer API
  (`explorer-api.cronos.org/mainnet/api/{v1,v2}`; helpers in `core/wallet.py`). **Daily PnL** → v1
  (`explorer_get`: `account/getTxsByAddress` + `account/getCRC20TransferByAddress`). **`/wallet` balances**
  → native v1 `account/getBalance` + **v2 Etherscan-style** (`_v2_get`: `tokentx` paginated over the *full*
  history for the complete token set, then `tokenbalance` per token; needs a `User-Agent`; scam/dust
  filtered, duplicate symbols disambiguated by contract, token set cached per wallet). This replaced the old keyless
  `cronos.org/explorer/api` feed, which silently froze for the wallet on 2026-05-22 while still
  returning `200 OK`. A **freshness guard** (`core/wallet.check_data_freshness`) compares the newest
  wallet block to the live chain tip (independent RPC) and fires a Telegram alert when data is far
  behind, so silent staleness can't recur. Requires `CRONOS_EXPLORER_API_KEY`. Response shape is
  Cronos-v1 (nested `from`/`to`, `transactionHash`/`timestamp`, token meta in `tokenMetadata`); the
  PnL path adapts rows to the legacy shape so `_normalize_etherscan_item`/`_aggregate_pnl` stay untouched.
- **prompts/** — prompt templates loaded via the client.
- **Railway** — 3 services: `bot`, `web-gpl6`, `worker`. Worker has a 5GB volume at `/data`.

## Current AI-provider state (split-brain — important)

- **Runtime → Claude.** `core/claude_client.py` calls Anthropic, model `claude-sonnet-4-6`.
  `app/main.py` and `core/pnl_calculator.py` import from it. Note: `claude_client.py` ends with
  `call_grok = call_claude`, so call sites still *read* "grok" but actually run Claude.
- **CI → still Grok.** `core/grok_client.py` still exists and posts to `api.x.ai` (`grok-4.3`).
  The GitHub Actions workflows call it via `.github/scripts/call_grok.py`. They still need `GROK_API_KEY`.

Finishing this migration is tracked in the implementation plan.

## Golden rules

- **Verify against live files** — never trust the stale SOT docs.
- **Smallest correct change.** Small PRs. Keep CI green.
- **Reuse `core/` helpers** instead of duplicating logic.
- **Defensive code** — timeouts + error handling on every external call (Cronos RPC, REST APIs, Telegram).
- **UTC** for all dates and time filters.
- **Telegram formatting** — Markdown v1 only: `**bold**` and simple `-`/`•` bullets. No tables, no code blocks (they break Telegram rendering).
- **Never hardcode or commit secrets.** Secrets live in Railway variables and GitHub secrets only.
- **Financial-decision-adjacent logic → flag for human review before shipping.** Simulate / dry-run any future on-chain action.
- **Never store the Railway token.** It is pasted per session.
- **Update the SOT docs in the same change as the code** so they stop drifting.

## Known issues / gotchas (verify each is still present before acting)

- `python-dotenv` is missing from `requirements.txt`, yet several modules do `from dotenv import load_dotenv` → import-failure risk.
- `core/pnl_calculator.py` raises `ValueError` at **import time** if `COVALENT_API_KEY` or `ETHERSCAN_API_KEY` is absent → module-level crash hazard.
- A dead Covalent code path still gates an import.
- `.env.example` contains a **real Etherscan/Cronoscan key in plaintext** → must be rotated and replaced with a placeholder.
- Worker start-command drift: `Procfile` says `python -u worker.py`; confirm `railway.toml` and `WORKER.md` agree.
- Orphaned / dead code: `telegram/handlers.py`, `app/health.py`, `app/github_webhook.py`, a dead `main.py` stub, and a local `telegram/` package that shadows the pip `telegram` package.
- No tagged releases; stale open PRs.

## Commands

```bash
pip install -r requirements.txt        # install (must include python-dotenv)
uvicorn app.main:app --reload          # run web service locally
python -u worker.py                    # run worker locally
```

Deploy: Railway (project + environment IDs are in the deployment docs / plan). Ensure
`ANTHROPIC_API_KEY` is set as a Railway variable before deploying.

## Environment variables

| Variable | Used by | Notes |
|----------|---------|-------|
| `ANTHROPIC_API_KEY` | runtime | required for all AI features |
| `GROK_API_KEY` | CI only | needed until the migration is finished |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | runtime | |
| `WALLET_ADDRESS`, `CRONOS_RPC_URL` | runtime | RPC also serves as the independent chain-tip reference for the freshness guard |
| `CRONOS_EXPLORER_API_KEY` | runtime | **required** — live Cronos Explorer v1 feed for balances + daily PnL |
| `CRONOS_STALE_BLOCK_THRESHOLD` | runtime (optional) | blocks-behind threshold for the stale-data alert (default 200000 ≈ 1 day) |
| `ETHERSCAN_API_KEY` | legacy | no longer used by the live data path (deprecated sync Covalent helper only) |

## Working with Claude Code on this repo

- **Use Plan Mode** for any multi-step change. Present the plan and get approval before editing.
- Follow `IMPLEMENTATION_PLAN.md` for the current stabilization work.
- After changes: confirm the app imports without env vars set, and that CI stays green.
