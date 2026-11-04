# Critical functions registry

These are the functions the bot cannot work correctly without. If one breaks, the owner either
hears nothing or is shown wrong numbers, and usually *silently*. Every change to one of them
needs a test and a Reviewer pass.

Each row names:
- the **invariant**: what must always stay true;
- the **auditor**: the agent that owns checking it (`.claude/agents/`).

The machine-checked copy of this list is `tests/test_critical_registry.py`. It fails if a
registered function disappears, and it ratchets test coverage: every critical function must be
referenced by a test, except the known gaps it lists. Keep the two in sync.

Selection rule: a function is critical if a defect in it causes one of these:
- (a) no message reaches the owner;
- (b) a wrong or missing money number;
- (c) a dead background loop;
- (d) a corrupted simulation record;
- (e) a stranger getting access.

## Tier 1: the bot can speak (delivery and routing) · auditor: `telegram-auditor`

| Function | Why critical | Invariant |
|---|---|---|
| `app/main.py` `send_telegram_message` | every bot reply goes through it | `**`→`*`; split at ≤4000 chars; plain-text retry on non-200; console mode never calls Telegram |
| `worker.py` `send_telegram` | every alert, the digest and the EOD report | same as above |
| `core/wallet.py` `send_telegram_alert` | data-source alerts | same as above; returns True only if Telegram accepted |
| `core/tg_format.py` `to_tg_markdown`, `split_message`, `plain_text` | formatting for all three senders | lossless split on line boundaries; fallback text has no markers |
| `app/main.py` `handle_command` | routes every command | every menu command reaches its handler; unknown → hint |
| `app/main.py` `telegram_webhook` | inbound when hosted | serves only allow-listed chats; always 200 |
| `run_local.py` `_telegram_poll_loop` | inbound when standalone | never steals a webhook; fails closed; never hot-loops |
| `core/telegram_webhook.py` `ensure_webhook` | self-heal when hosted | "restored" only after a confirming read-back |

## Tier 2: the numbers are right (wallet and daily report) · auditor: `wallet-data-auditor`

| Function | Why critical | Invariant |
|---|---|---|
| `core/wallet.py` `get_wallet_balances` | /wallet, portfolio alerts | a failed source → `ok=False`, never "$0"; holdings removed only on a confirmed zero |
| `core/wallet.py` `_discover_token_set` | which tokens exist at all | a failed page is never treated as the end of history |
| `core/wallet.py` `parse_raw_balance` | each token amount | non-numeric results are failures, not zero |
| `core/wallet.py` `explorer_get`, `_v2_get` | every Explorer read | timeout, never raises, failures visible in logs |
| `core/wallet.py` `get_token_prices` | USD values | Cronos pairs only; best-liquidity pool wins |
| `core/wallet.py` `check_data_freshness` | catches a frozen data source | compares against the independent RPC tip |
| `core/pnl_calculator.py` `get_today_transactions_async` | daily report input | a fetch failure is reported, not shown as an empty day; the endBlock bound is not below the chain tip |
| `core/pnl_calculator.py` `_aggregate_pnl` | daily report math | net = in − out per token; failed transactions skipped |
| `core/pnl_calculator.py` `get_daily_pnl_report` | /daily_pnl + EOD text | honest labels (net flow, not P&L); AI failure → base report |

## Tier 3: the scanner and the simulation · auditors: `scanner-auditor`, `simulation-auditor`

| Function | Why critical | Invariant |
|---|---|---|
| `worker.py` `poll_new_pools` | the discovery loop | never dies; one message per cycle; dedup by `{chain}:{pool}` |
| `core/pair_discovery.py` `fetch_new_pools`, `fetch_pool_prices` | all pool data | 429 backoff; never raises; fetch status recorded |
| `core/pair_discovery.py` `parse_gt_pool`, `classify_pool` | pool shape and age | bad fields → safe defaults; young pools held, not scored |
| `worker.py` `score_pair` | alert quality | 0-100; nan/inf → 0 points; transparent ingredients |
| `core/paper_trading.py` `check_exit`, `close_position` | simulated P&L | TP books at the threshold; SL books at the observed price; a missing price never exits |
| `core/paper_trading.py` `load_state`, `repair_impossible_trades`, `reconcile_balance` | simulation record | a corrupt file is backed up, never lost; balance = start + realized − open cost |
| `worker.py` `_paper_step` | the simulation engine | a paper bug never breaks the scanner; one note per entry and per exit |

## Tier 4: the runtime stays up · auditor: `runtime-auditor`

| Function | Why critical | Invariant |
|---|---|---|
| `worker.py` `main` | starts every loop | each loop catches its own errors; one crash doesn't stop the others |
| `worker.py` `scheduled_eod_pnl`, `scheduled_scan_digest` | daily messages | fire once per Athens day at the configured time, also across DST |
| `worker.py` `portfolio_watch`, `detect_portfolio_moves` | price-move alerts | first sighting only seeds; cooldown respected; never alerts on restart |
| `run_local.py` `_amain` | the standalone runtime | console mode ↔ no Telegram; the poller and the worker start together |
| `core/claude_client.py` `call_claude` | AI text | timeout; any failure → an error prefix that callers detect |
