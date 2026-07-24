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

## Active roadmap

- **Strategy engine (simulation) — ACTIVE (2026-07-17).** `core/paper_trading.py` + the worker
  simulate entries/exits with imaginary money to produce evidence about the scanner's judgment.
  See the Paper-trading block under Worker for the rules.
- **STANDING GATE — real-fund execution does not exist in this codebase.** No private keys, no
  signing, no spending capability anywhere. Real execution only becomes DISCUSSABLE after the
  simulation produces evidence AND explicit risk controls exist; any such step is
  financial-decision-adjacent: human review + simulate/dry-run first (golden rules).
- **Trading execution — future, not built.** When (and only when) real trading steps land, the AI's
  "actionable trading insights" / recommendation language may return to the system prompt and the
  runtime prompts. It was removed on 2026-07-05 so the AI's claimed identity matches actual
  capabilities (Cronos-only monitoring analyst; observations are information, not financial advice).

## Architecture

- **Web service** — `app/main.py` (FastAPI + uvicorn). Telegram webhook at `/telegram/webhook`,
  wallet analysis at `/grok/analyze`, daily PnL, health at `/` and `/health`.
- **Worker** — `worker.py`. Polls Dexscreener for new Cronos pairs, monitors the wallet, sends a
  heartbeat, runs end-of-day PnL. **Persistence (verified 2026-07-13):** the 5GB volume `worker-persistence-GNKn` is mounted at `/data`; the path resolves via `WORKER_DATA_DIR` (explicit override) → `RAILWAY_VOLUME_MOUNT_PATH` (auto-set by Railway to `/data`) → `./data` (local dev). Production writes `/data/known_pairs.json`, so known-pairs (and future paper-trading state) genuinely survive redeploys; a loud log warning fires only if neither env var is set (ephemeral). **Multi-chain discovery (2026-07-23, `core/pair_discovery.py`):**
  the Dexscreener `search?q=cronos` feed returned established pairs ranked by relevance (0 passed
  newness), so it was replaced by GeckoTerminal `new_pools` (keyless, ~48h of genuinely new pools,
  30 calls/min) polled once per enabled chain per cycle. `CHAINS_ENABLED` (default
  `cro,solana,sui-network`); per-chain floors `PAIR_MIN_LIQUIDITY_USD_{CHAIN}` (defaults cro 5000,
  solana 10000, sui-network 10000 — Solana is a junk firehose, Cronos nearly barren) and
  `PAIR_MIN_SCORE_{CHAIN}` (falls back to global `PAIR_MIN_SCORE`). **Maturity rule:** a pool
  younger than `PAIR_MIN_AGE_MINUTES` (20) has no volume/tx history yet (scoring it would score
  ~0), so it is HELD in a persisted pending-maturity set (`pending_pools.json`, sibling to
  `known_pairs.json` on the volume), re-evaluated each cycle, and dropped only past
  `PAIR_NEWNESS_WINDOW_HOURS` (24). Dedup is keyed `{chain}:{pool_address}` (was a bare pair address pre-2026-07-23; old keys in `known_pairs.json` become inert, so a still-live pair may re-alert at most once under its new key). GeckoTerminal fields
  are mapped into the UNCHANGED `score_pair` 0-100 math; one combined Telegram message per cycle,
  each alert labelled with chain + DEX, 🔥 >=70 / 👀 >=35 (detail for first 10, capped 4000 chars).
  429 backoff; the loop never dies on a feed failure. The Dexscreener token-pricing used by
  `/wallet` is a different endpoint and is untouched. **Quality score (2026-07-06):** each passing pair gets a
  transparent 0-100 score (`worker.score_pair`, unit-tested offline) — four ingredients worth
  0-25 points each. What raises the score: 1h volume (full 25 pts at `PAIR_SCORE_VOL1H_FULL`,
  default $25k), buy pressure above 50% buys in the last hour (full at
  `PAIR_SCORE_BUY_RATIO_FULL`, a FRACTION, default 0.85), positive 1h price momentum (full at
  `PAIR_SCORE_MOM1H_FULL` percent, default +30), and liquidity depth (full 25 pts at
  `PAIR_SCORE_LIQ_FULL`, default $50k). What lowers it: thin volume, sell-heavy or dead
  transaction flow (a no-transactions hour scores 0 buy-pressure points), flat or negative
  price action, and shallow liquidity — each simply earns fewer of its 25 points; nan/inf
  from the API count as 0. Only pairs at or above `PAIR_MIN_SCORE` (default 35) are alerted,
  labeled 🔥 strong (>=70) or 👀 notable; the alert shows the ingredients (1h volume,
  buys/sells, 1h change, liquidity, age), not just the verdict. Below-bar pairs are skipped
  silently and counted in the log; if never alerted they are NOT marked seen (so they can
  still qualify later in their 24h window), while an already-alerted pair that dips below the
  bar keeps its last_seen fresh so a recovery does not re-alert it. **Portfolio-watch
  (2026-07-06):** `worker.portfolio_watch` (gated by `PORTFOLIO_WATCH_ENABLED`, default on)
  checks the owner's holdings every `PORTFOLIO_WATCH_INTERVAL_MIN` (default 5 min) by reusing
  `core.wallet.get_wallet_balances` (balances + Dexscreener pricing — no duplicated logic;
  note this also runs the freshness guard each cycle — its Telegram alert is therefore
  throttled to one per `CRONOS_STALE_ALERT_COOLDOWN_SECONDS`, default 6h; the log line still
  fires every check). Priced holdings worth >= `PORTFOLIO_MIN_USD` (default $5, CRO included;
  the bar is an ENTRY criterion — a holding that crashes below it stays watched so dumps
  still alert) are tracked against a rolling baseline;
  a move of >= `PORTFOLIO_MOVE_THRESHOLD_PCT` (default 10%) alerts with direction, %, price
  then->now, and the holding's USD value then->now — all movers in one cycle in ONE message,
  max one alert per token per `PORTFOLIO_ALERT_COOLDOWN_MIN` (default 60). The baseline
  rebases on alert and lives IN MEMORY ONLY: without the Railway Volume caveat changing,
  a redeploy/restart quietly re-seeds it (first cycle seeds, alerts from the second cycle
  onward — never a false alert on restart). State machine is pure
  (`worker.detect_portfolio_moves` / `worker.watch_holdings`) and unit-tested offline. **Scanner
  digest (2026-07-16, per-chain 2026-07-23):** `worker.scheduled_scan_digest` (gated by
  `SCAN_DIGEST_ENABLED`, default on) sends ONE summary per day at `SCAN_DIGEST_HOUR` (default 21,
  Europe/Athens), now PER CHAIN: e.g. `🔎 Scanner digest — cro: seen 5, matured 3, passed 0 ·
  solana: seen 20, matured 14, passed 2, best 71 (MOON) · sui: seen 20, matured 18, passed 1, best 58 (SPX) ·
  sent 3`. Counters are in-memory (restart restarts the window); no quality threshold is changed.
  Fold + formatter are pure (`worker.record_chain_funnel` / `worker.format_multichain_digest`),
  unit-tested offline. (The old single-chain `record_pair_funnel`/`format_scan_digest` remain in
  the file, unused, so their tests stay green.) **Paper
  trading (2026-07-17, SIMULATION ONLY):** `core/paper_trading.py` + `worker._paper_step`,
  gated by `PAPER_TRADING_ENABLED` (default on — it risks nothing; no keys, no real orders).
  Starts with `PAPER_STARTING_USD` (default $1000) of simulated money. Entry: an ALERTED pair
  scoring >= `PAPER_ENTRY_SCORE` (default 70, the 🔥 tier) opens a `PAPER_POSITION_USD`
  (default $50) position at the alert's price — max `PAPER_MAX_OPEN` (5) concurrent, skip when
  full/broke/duplicate. Exits checked every polling cycle via ONE batched Dexscreener call for
  open positions (zero extra Explorer calls): take-profit +`PAPER_TP_PCT`% (25), stop-loss
  -`PAPER_SL_PCT`% (15), time-stop `PAPER_MAX_HOLD_HOURS` (24) — first hit wins; a missing
  price NEVER exits (hold + log only). Every entry/exit sends ONE 🧪-marked Telegram note with
  pair, price, size, reason, and running simulated balance. State (balance/open/closed) lives
  in `paper_state.json` on the /data volume (atomic writes, corrupt-file-safe loads, survives
  redeploys). Decision logic is pure (`should_enter`/`check_exit`/close math) and unit-tested
  offline. Expectation: with the 🔥-tier entry bar, days may pass before the first simulated
  trade — patience IS the strategy. **Webhook self-heal (2026-07-18):** after the webhook was
  found pointing at the deleted web-gpl6 (404, pending updates stuck), two defenses ship:
  (a) the bot sets its OWN webhook on startup (`app/main.py` startup hook, gated by
  `WEBHOOK_AUTOSET_ENABLED`, default on; target = `WEBHOOK_URL` > `APP_URL` >
  `RAILWAY_PUBLIC_DOMAIN` > canonical bot domain); (b) the worker runs `webhook_guard`
  (gated by `WEBHOOK_GUARD_ENABLED`, default on) every `WEBHOOK_GUARD_INTERVAL_MIN`
  (default 60): on drift vs `WEBHOOK_EXPECTED_URL` (default canonical) it re-sets, READS
  BACK to confirm, and sends one alert '🛡 Webhook drift detected and auto-restored'.
  Logic is pure + offline-tested (`core/telegram_webhook.py`); a set without a confirming
  read-back reports 'failed', never success. Caveats: any SECOND web service running this
  codebase must set `WEBHOOK_AUTOSET_ENABLED=false` (or an explicit `WEBHOOK_URL`), else it
  re-claims the webhook on each of its restarts until the guard heals it (≤1h); and
  `WEBHOOK_EXPECTED_URL` (worker) must equal the bot's resolved target, or the pair will trade
  the webhook once per bot restart (alerting each time). Defaults converge today. **/paper + mirror (2026-07-17):** the /data volume attaches
  ONLY to the worker, so the bot cannot read `paper_state.json`; after every engine step the
  worker POSTs a compact state mirror to the bot's `POST /internal/paper-state` (auth =
  sha256 of the shared `TELEGRAM_BOT_TOKEN`, token never sent; in-memory, refills ≤1 cycle
  after a bot restart; override target via `PAPER_MIRROR_URL`). `/paper` renders from the
  mirror (renderer `app/commands/paper.py`, pure + unit-tested): balance + realized PnL since
  start, open positions with entry/current/unrealized (current prices via one keyless
  Dexscreener batch; 'price unknown' if unavailable), last 10 closed with win/loss + reason,
  win rate; stale mirror (>30 min) is flagged. The daily EOD report gains one line:
  `🧪 Paper: balance $X · open Y · closed Z · win rate W%`.
- **core/** — shared helpers. `claude_client.py` (AI calls), `wallet.py`, `pnl_calculator.py`,
  `price_service.py`, Dexscreener access. **Reuse these; do not duplicate their logic in `app/` or `worker/`.**
- **Blockchain data source (2026-06-21, balances rev. 2026-06-24).** Live, keyed Cronos Explorer API
  (`explorer-api.cronos.org/mainnet/api/{v1,v2}`; helpers in `core/wallet.py`). **Daily PnL** → v1
  (`explorer_get`: `account/getTxsByAddress` + `account/getCRC20TransferByAddress`). **`/wallet` balances**
  → native v1 `account/getBalance` + **v2 Etherscan-style** (`_v2_get`: `tokentx` paginated over the *full*
  history for the complete token set, then `tokenbalance` per token; needs a `User-Agent`; scam/dust
  filtered, duplicate symbols disambiguated by contract, token set cached per wallet). **USD values (2026-07-05):** `core/wallet.get_token_prices` batches Dexscreener
  `latest/dex/tokens/{addrs}` (30/call, cronos pairs only, best-liquidity pool wins; CRO via the
  WCRO contract); `/wallet` shows a portfolio total, sorts by USD desc, collapses holdings under
  `WALLET_MIN_USD_DISPLAY` (default $1), marks unpriced tokens 'price unknown', and falls back to
  the plain amounts-only output if pricing fails entirely (renderer: `app/commands/balances.py`). **Efficiency
  (2026-07-13):** the Explorer v2 API has no all-balances endpoint, so the balance path no
  longer fires one `tokenbalance` per historical contract every cycle (~197, which caused the
  429s). It now caches discovery for `WALLET_DISCOVERY_TTL_HOURS`, pre-filters scam-by-name
  with no API call, keeps a per-wallet held-set and only balance-checks real holdings each
  cycle (full sweep of all candidates every `WALLET_BALANCE_REFRESH_HOURS`), and backs off on
  429 (`WALLET_V2_MAX_RETRIES`). A held token keeps its last known amount on a transient
  failure instead of flickering to 0. A failed native `getBalance` now returns `ok=False` so
  `/wallet /bal /balances` reply 'data source unavailable' instead of '$0 / no tokens'
  (2026-07-13). **PnL honesty (2026-07-17):** `get_today_transactions_async` returns
  `(txs, fetch_ok)`; any Explorer failure (HTTP error / 429 / rejected key / exception —
  partial failures included) sets `fetch_ok=False` and counts as stale for the freshness
  guard (`note_fetch_failure`, same throttle), so `get_daily_pnl_report` — the string
  /daily_pnl replies AND the automatic EOD send wraps with its header — answers
  "⚠️ Couldn't fetch transaction data right now" instead of "No meaningful transactions
  found today". A successful fetch on a genuinely empty day still gets the classic line. This replaced the old keyless
  `cronos.org/explorer/api` feed, which silently froze for the wallet on 2026-05-22 while still
  returning `200 OK`. A **freshness guard** (`core/wallet.check_data_freshness`) compares the newest
  wallet block to the live chain tip (independent RPC) and fires a Telegram alert when data is far
  behind, so silent staleness can't recur. Requires `CRONOS_EXPLORER_API_KEY`. Response shape is
  Cronos-v1 (nested `from`/`to`, `transactionHash`/`timestamp`, token meta in `tokenMetadata`); the
  PnL path adapts rows to the legacy shape so `_normalize_etherscan_item`/`_aggregate_pnl` stay untouched.
- **prompts/** — Claude-native runtime templates (2026-07-05): `claude_daily_pnl.txt`,
  `claude_wallet_analysis.txt` (+ CI's `claude_code_review.txt`, `claude_health_check.txt`).
  Grok-era prompts were archived to `archive/prompts/` — except `grok_market_analysis.txt`,
  which stays because gated `core/market_analysis.py` (default off) still loads it.
- **Railway** — 3 services: `bot`, `web-gpl6`, `worker`. Worker has a 5GB volume at `/data`.

## Current AI-provider state (Claude-only as of 2026-07-04)

- **Runtime → Claude.** `core/claude_client.py` calls Anthropic, model `claude-sonnet-4-6`,
  `max_tokens=2048`; `DEFI_SYSTEM_PROMPT` = Cronos-only monitoring analyst (2026-07-05).
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
- **UTC** for all internal timestamps and time filters. One deliberate exception: the **daily PnL
  reporting day boundary is Europe/Athens** (`REPORT_TZ` in `core/pnl_calculator.py`), matching the
  worker's Athens-scheduled EOD send, so the report covers the owner's local day. (2026-07-05)
- **Telegram formatting** — Markdown v1 only: `**bold**` and simple `-`/`•` bullets. No tables, no code blocks (they break Telegram rendering).
- **Never hardcode or commit secrets.** Secrets live in Railway variables and GitHub secrets only.
- **Financial-decision-adjacent logic → flag for human review before shipping.** Simulate / dry-run any future on-chain action.
- **Never store the Railway token.** It is pasted per session.
- **Update the SOT docs in the same change as the code** so they stop drifting.
- **No write-action (delete, deploy, settings change, webhook change) is DONE until a read-back
  check confirms the new state. Staged ≠ applied. Reported ≠ real.** (2026-07-18)
- **Before editing anything, verify the local clone matches origin/main (git fetch + SHA compare).
  Never edit or commit from a stale checkout.** (2026-07-18)

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
  `prompts/grok_market_analysis.txt` (other grok prompts archived 2026-07-05) — retiring these is a
  separate approved-later step.
- No tagged releases; stale open PRs/branches.

## Token rotation

- `docs/TOKEN_ROTATION_RUNBOOK.md` (2026-07-17, amended 2026-07-18) is the prepared,
  NOT-yet-executed procedure for rotating the Telegram bot token. Since 2026-07-18 the bot
  DOES set its own webhook on startup (see webhook self-heal), so rotation = BotFather revoke
  → update `TELEGRAM_BOT_TOKEN` in Railway → redeploy (webhook auto-registers with the new
  token) → the runbook's manual `setWebhook` step becomes a verification, not a requirement.

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
| `CRONOS_STALE_ALERT_COOLDOWN_SECONDS` | runtime (optional) | min seconds between stale-data Telegram alerts (default 21600 = 6h; logs are not throttled) |
| `WALLET_MIN_USD_DISPLAY` | web (optional) | /wallet holdings under this USD value collapse into one line (default 1) |
| `WALLET_DISCOVERY_TTL_HOURS`, `WALLET_BALANCE_REFRESH_HOURS` | runtime (optional) | hours between token re-discovery / full balance sweeps (default 6 / 6) |
| `WALLET_BALANCE_CONCURRENCY`, `WALLET_V2_MAX_RETRIES` | runtime (optional) | concurrent tokenbalance reads / 429 backoff retries (default 8 / 3) |
| `PAIR_NEWNESS_WINDOW_HOURS` | worker (optional) | new-pair alert window vs `pairCreatedAt` (default 24) |
| `PAIR_MIN_LIQUIDITY_USD` | worker (optional) | minimum pool liquidity for a new-pair alert (default 10000) |
| `CHAINS_ENABLED` | worker (optional) | comma list of GeckoTerminal networks to scan (default `cro,solana,sui-network`) |
| `PAIR_MIN_LIQUIDITY_USD_{CHAIN}` | worker (optional) | per-chain liquidity floor (defaults CRO 5000, SOLANA 10000, SUI_NETWORK 10000); `{CHAIN}` = upper, `-`→`_` |
| `PAIR_MIN_SCORE_{CHAIN}` | worker (optional) | per-chain score bar (falls back to `PAIR_MIN_SCORE`) |
| `PAIR_MIN_AGE_MINUTES` | worker (optional) | pools younger than this are held pending maturity, not scored (default 20) |
| `DISCOVERY_INTERVAL` | worker (optional) | seconds between discovery cycles (default 300) |
| `PAIR_MIN_SCORE` | worker (optional) | minimum 0-100 quality score for a new-pair alert (default 35) |
| `PAIR_SCORE_VOL1H_FULL`, `PAIR_SCORE_BUY_RATIO_FULL`, `PAIR_SCORE_MOM1H_FULL`, `PAIR_SCORE_LIQ_FULL` | worker (optional) | level at which each ingredient earns its full 25 pts: 1h volume USD / buy ratio as a fraction in (0.5, 1] / 1h change percent / liquidity USD (defaults 25000 / 0.85 / 30 / 50000) |
| `WORKER_DATA_DIR` | worker (optional) | explicit persistence dir; else `RAILWAY_VOLUME_MOUNT_PATH` (=/data in prod) else `./data` |
| `PORTFOLIO_WATCH_ENABLED` | worker (optional) | portfolio price-move alerts on held tokens (default true) |
| `PORTFOLIO_WATCH_INTERVAL_MIN`, `PORTFOLIO_MOVE_THRESHOLD_PCT`, `PORTFOLIO_MIN_USD`, `PORTFOLIO_ALERT_COOLDOWN_MIN` | worker (optional) | check cadence min / alert threshold % vs rolling baseline / min holding USD watched / per-token alert cooldown min (defaults 5 / 10 / 5 / 60) |
| `PAPER_TRADING_ENABLED` | worker (optional) | paper-trading simulation on/off (default true; simulation only, no real orders possible) |
| `WEBHOOK_AUTOSET_ENABLED` | bot (optional) | bot claims its own webhook on startup (default true) |
| `WEBHOOK_GUARD_ENABLED`, `WEBHOOK_GUARD_INTERVAL_MIN`, `WEBHOOK_EXPECTED_URL` | worker (optional) | hourly drift guard on/off / cadence min / expected URL (defaults true / 60 / canonical bot domain) |
| `PAPER_MIRROR_URL` | worker (optional) | where the worker pushes the /paper state mirror (default the bot's public /internal/paper-state) |
| `PAPER_STARTING_USD`, `PAPER_ENTRY_SCORE`, `PAPER_POSITION_USD`, `PAPER_MAX_OPEN`, `PAPER_TP_PCT`, `PAPER_SL_PCT`, `PAPER_MAX_HOLD_HOURS` | worker (optional) | simulated capital / entry score bar / position size / max concurrent / take-profit % / stop-loss % / time-stop hours (defaults 1000 / 70 / 50 / 5 / 25 / 15 / 24) |
| `SCAN_DIGEST_ENABLED`, `SCAN_DIGEST_HOUR` | worker (optional) | daily scanner-funnel digest on/off + Athens hour (default true / 21) |
| `EOD_PNL_ENABLED`, `EOD_PNL_HOUR` | worker (optional) | automatic EOD PnL send (default off, hour 0 Athens). **With the Athens reporting boundary, hour 0 fires on the just-started (empty) day — set `EOD_PNL_HOUR=23` on Railway before enabling.** |
| `ETHERSCAN_API_KEY` | legacy | no longer used by the live data path (deprecated sync Covalent helper only) |

## Working with Claude Code on this repo

- **Use Plan Mode** for any multi-step change. Present the plan and get approval before editing.
- Follow `IMPLEMENTATION_PLAN.md` for the current stabilization work.
- After changes: confirm the app imports without env vars set, and that CI stays green.
- **Railway MCP server** — `.mcp.json` registers the `railway` server (HTTP,
  `https://mcp.railway.com`) at project scope, so Claude Code sessions can manage the Railway
  deployment directly. The file stores **no credentials**: authentication is per-session OAuth
  (run `/mcp` to connect), consistent with the golden rule that the Railway token is never
  stored. (2026-07-17)
