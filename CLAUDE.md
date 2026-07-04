# CLAUDE.md

Project memory for Claude Code. Read this fully before doing anything in this repo.

---

## ⚠️ Read this first: the code is the source of truth

The stale Grok-era "source of truth" docs (`GROK_USAGE.md`, `GROK_COORDINATION.md`,
`AGENTS.md`, `project-awareness.md`, `docs/project-status.md`, `SUMMARY.md`, `GROK_HEALTH.md`)
and the `agents/` orchestration folder were **moved to `archive/` on 2026-07-04**. They describe
Grok as the bot's brain — that stopped being true when the runtime migrated to Claude. Nothing
in `archive/` is load-bearing; do not act on it. Always verify claims against the actual code.
When any doc and the code disagree, the code wins — and fix the doc.

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

## Current AI-provider state (Claude-only as of 2026-07-04)

- **Runtime → Claude.** `core/claude_client.py` calls Anthropic, model `claude-sonnet-4-6`.
  `app/main.py` and `core/pnl_calculator.py` import from it. Note: `claude_client.py` ends with
  `call_grok = call_claude`, so call sites still *read* "grok" but actually run Claude.
- **CI → Claude-only.** `claude-code-review.yml` (on PR) + `claude-health-check.yml` (scheduled) use
  `.github/scripts/call_claude.py` (`ANTHROPIC_API_KEY`); both are advisory (`continue-on-error`).
  Only `ci.yml` (import smoke-test + pytest) gates. The legacy Grok workflows
  (`grok-code-review.yml`, `health-check.yml`) were **removed on 2026-07-04**; `GROK_API_KEY` is no
  longer required anywhere in CI.
- **Remaining real-Grok code (in-tree, gated off — retirement is a separate later step):**
  `core/grok_client.py` (`api.x.ai`) is still imported by `.github/scripts/call_grok.py` (now unused
  by any workflow) and `core/market_analysis.py` (worker EOD market-context, env-gated by
  `MARKET_ANALYSIS_ENABLED`, default **false**). `agents/orchestrator.py` was archived to
  `archive/agents/`. The bot's user-facing command paths do **not** use real Grok.

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

**Resolved (kept for history):**
- ✅ `python-dotenv` is now in `requirements.txt`. (2026-06-24)
- ✅ `core/pnl_calculator.py` no longer raises at **import time** — `COVALENT_API_KEY`/`ETHERSCAN_API_KEY`
  are read lazily inside functions (`_get_covalent_api_key`/`_get_etherscan_api_key`); the module imports
  with no env vars set. (The legacy sync Covalent path still exists but no longer gates the import.) (2026-06-24)
- ✅ `.env.example` no longer holds a real key — `ETHERSCAN_API_KEY=**REDACTED**` placeholder. (Key
  **rotation** at the provider is a separate manual user action and can't be verified from the repo.) (2026-06-24)
- ✅ Corrupt committed file `GROK_REPO_ANALYSIS_REPORT.md` (~10.5k null bytes) **deleted**. (2026-07-04)
- ✅ `.claude/settings.local.json` is now **gitignored** — a blanket `git add .` can no longer commit it. (2026-07-04)
- ✅ Grok CI workflows removed; Grok-era SOT docs and `agents/` archived to `archive/`. (2026-07-04)

**Still open:**
- Worker start-command drift: `Procfile` + `railway.toml` use `python -u worker.py`, but the `Dockerfile`
  `CMD` is `python worker.py` (no `-u`); confirm `WORKER.md` agrees.
- Orphaned / dead code: `telegram/handlers.py`, `app/health.py`, `app/github_webhook.py`, a dead `main.py`
  stub, and a local `telegram/` package that shadows the pip `telegram` package.
- Leftover gated Grok code: `core/grok_client.py`, `core/market_analysis.py`, `.github/scripts/call_grok.py`,
  `prompts/grok_*.txt` — retiring these is a separate approved-later step.
- No tagged releases; stale open PRs/branches.

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
| `GROK_API_KEY` | — (removed) | legacy; only needed if the gated `core/grok_client.py` paths are ever revived |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | runtime | |
| `WALLET_ADDRESS`, `CRONOS_RPC_URL` | runtime | RPC also serves as the independent chain-tip reference for the freshness guard |
| `CRONOS_EXPLORER_API_KEY` | runtime | **required** — live Cronos Explorer v1 feed for balances + daily PnL |
| `CRONOS_STALE_BLOCK_THRESHOLD` | runtime (optional) | blocks-behind threshold for the stale-data alert (default 200000 ≈ 1 day) |
| `ETHERSCAN_API_KEY` | legacy | no longer used by the live data path (deprecated sync Covalent helper only) |

## Working with Claude Code on this repo

- **Use Plan Mode** for any multi-step change. Present the plan and get approval before editing.
- Follow `IMPLEMENTATION_PLAN.md` for the current stabilization work.
- After changes: confirm the app imports without env vars set, and that CI stays green.
