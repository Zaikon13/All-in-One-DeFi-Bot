# core/pnl_calculator.py - Simple & Working Daily PnL Calculator

import os
import logging
from datetime import datetime, timezone
from typing import List, Dict

import httpx

# Reuse Grok client (core/ preferred over duplication in app/main.py)
from core.grok_client import call_grok, load_prompt

# Require API keys from environment; do NOT fall back to hardcoded defaults.
COVALENT_API_KEY = os.getenv("COVALENT_API_KEY")
if not COVALENT_API_KEY:
    raise ValueError("COVALENT_API_KEY is missing from environment variables")

WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")

# Etherscan V2 (for async production /daily_pnl path only). Legacy sync path remains on Covalent.
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
if not ETHERSCAN_API_KEY:
    raise ValueError("ETHERSCAN_API_KEY is missing from environment variables")

COVALENT_BASE = "https://api.covalenthq.com/v1"


def get_today_transactions() -> List[Dict]:
    """Fetch today's transactions (simple & reliable)"""
    if not WALLET_ADDRESS:
        print("[ERROR] Missing WALLET_ADDRESS")
        return []

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")  # UTC for tx date filter (minimal targeted fix approved by Review Agent 2026-05-28)
    url = f"{COVALENT_BASE}/25/address/{WALLET_ADDRESS}/transactions_v3/?key={COVALENT_API_KEY}"

    try:
        with httpx.Client(timeout=30) as client:
            r = client.get(url)
            if r.status_code == 200:
                data = r.json()
                items = data.get("data", {}).get("items", [])
                today_tx = [tx for tx in items if tx.get("block_signed_at", "").startswith(today)]
                return today_tx
            else:
                print(f"[ERROR] Covalent status {r.status_code}")
    except Exception as e:
        print(f"[ERROR] {str(e)}")
    return []


def calculate_daily_pnl() -> Dict:
    """Calculate simple but correct daily PnL"""
    transactions = get_today_transactions()
    if not transactions:
        return {"error": "No transactions found today or API error."}

    token_data = {}

    for tx in transactions:
        for transfer in tx.get("transfers", []):
            symbol = transfer.get("contract_ticker_symbol", "CRO")
            decimals = transfer.get("contract_decimals", 18)
            amount = int(transfer.get("delta", 0)) / (10 ** decimals)
            tx_type = "BUY" if amount > 0 else "SELL"
            amount = abs(amount)

            if symbol not in token_data:
                token_data[symbol] = {"buys": 0, "sells": 0, "trades": []}

            if tx_type == "BUY":
                token_data[symbol]["buys"] += amount
            else:
                token_data[symbol]["sells"] += amount

            token_data[symbol]["trades"].append({
                "time": tx.get("block_signed_at", "")[11:16],
                "type": tx_type,
                "amount": round(amount, 4),
                "symbol": symbol
            })

    result = []
    for symbol, data in token_data.items():
        net = data["buys"] - data["sells"]
        result.append({
            "symbol": symbol,
            "trades": len(data["trades"]),
            "net": round(net, 4),
            "trades_list": data["trades"]
        })

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "tokens": result
    }


def format_pnl_report(data: Dict) -> str:
    """Format clean report"""
    if "error" in data:
        return data["error"]

    lines = [f"📊 **Daily PnL Report** ({data['date']})"]
    lines.append(f"\n🔑 Wallet: {WALLET_ADDRESS[:6]}...{WALLET_ADDRESS[-4:]}")
    lines.append("")

    for token in data["tokens"]:
        lines.append(f"**{token['symbol']}** ({token['trades']} trades)")
        for t in token["trades_list"]:
            lines.append(f"{t['time']} | {t['type']} {t['amount']} {token['symbol']}")
        lines.append(f"**Net:** {token['net']:+.4f} {token['symbol']}")
        lines.append("")

    return "\n".join(lines)


# -------------------------------------------------------------------
# Production async formatter for improved /daily_pnl quality (Option A, post-Review Agent 2026-05-28)
# Per refined brief: new function called EXCLUSIVELY from inside get_daily_pnl_report().
# Implements clean aggregates + Top Movers (Python-owned) + optional Grok insight (commentary only).
# -------------------------------------------------------------------
def format_daily_pnl_report(data: Dict, grok_insight: str | None = None) -> str:
    """Clean, modern daily PnL report for the production async path only.

    Production async formatter (used only by get_daily_pnl_report).
    Legacy sync path (telegram/handlers.py) continues to use the original format_pnl_report() unchanged.

    Post-Review Agent clarifications incorporated:
    - Grok Output Contract: Grok returns ONLY 3-6 sentence qualitative paragraph (no data/numbers/headers).
    - Telegram Markdown Safety: defensive comment on append; prompt enforces **bold** + simple lists only.
    - All structure/numbers computed here safely in Python.
    """
    if "error" in data:
        return data["error"]

    date = data.get("date", "today")
    tokens = data.get("tokens", [])
    wallet = WALLET_ADDRESS or "unknown"
    preview = f"{wallet[:6]}...{wallet[-4:]}" if len(wallet) > 10 else wallet

    total_trades = sum(t.get("trades", 0) for t in tokens)
    active_token_count = len(tokens)

    # Top movers by |net| (pre-computed for prompt + report; Python side only)
    sorted_tokens = sorted(tokens, key=lambda t: abs(t.get("net", 0)), reverse=True)
    top_movers = sorted_tokens[:5]

    lines = [
        f"📊 **Daily PnL — {date}**",
        "",
        f"🔑 Wallet: {preview}",
        f"Active tokens: {active_token_count} | Total trades: {total_trades}",
        "",
    ]

    if top_movers:
        lines.append("**Top Movers** (by |net delta|)")
        for t in top_movers:
            lines.append(f"• {t['symbol']} — net {t['net']:+.4f} ({t['trades']} trades)")
        lines.append("")

    if grok_insight:
        # Grok insight appended raw. Prompt strictly constrains output to safe Telegram Markdown v1.
        # If future changes relax the prompt, consider adding light escaping here.
        # (Review Agent clarification #2)
        lines.append("🤖 **Grok Daily Insight:**")
        lines.append(grok_insight.strip())
        lines.append("")

    return "\n".join(lines)


# -------------------------------------------------------------------
# Shared pure aggregation logic (reused by sync + async paths to avoid duplication)
# -------------------------------------------------------------------
def _aggregate_pnl(transactions: List[Dict]) -> Dict:
    """Pure function: aggregates Covalent tx list into daily net-delta PnL structure.
    Used by production async path only (via calculate_daily_pnl_async / get_daily_pnl_report).
    Legacy sync calculate_daily_pnl() + get_today_transactions() remain UNCHANGED (exact duplicate logic preserved for telegram/handlers.py compatibility).
    Improvements (flow from async fetcher + here):
      - transfers[] processed first for every tx
      - conservative log_events ERC20 "Transfer" parsing with strict dedup
      - minimal native CRO via top-level tx["value"] (last)
    All changes minimal + defensive. Output shape identical.
    """
    if not transactions:
        return {"error": "No transactions found today or API error."}

    token_data = {}

    for tx in transactions:
        # Filter to successful tx only (data quality; minimal targeted fix approved by Review Agent 2026-05-28)
        if not tx.get("successful", True):
            continue

        # transfers[] FIRST (Review Agent 2026-05-30 guardrail)
        symbols_with_transfer_delta = set()
        for transfer in tx.get("transfers", []):
            symbol = transfer.get("contract_ticker_symbol", "CRO")
            decimals = transfer.get("contract_decimals", 18)
            amount = int(transfer.get("delta", 0)) / (10 ** decimals)
            tx_type = "BUY" if amount > 0 else "SELL"
            if amount != 0:
                symbols_with_transfer_delta.add(symbol)
            amount = abs(amount)

            if symbol not in token_data:
                token_data[symbol] = {"buys": 0, "sells": 0, "trades": []}

            if tx_type == "BUY":
                token_data[symbol]["buys"] += amount
            else:
                token_data[symbol]["sells"] += amount

            token_data[symbol]["trades"].append({
                "time": tx.get("block_signed_at", "")[11:16],
                "type": tx_type,
                "amount": round(amount, 4),
                "symbol": symbol
            })

        # Improved transfer detection: conservative log_events parsing for standard ERC20 Transfer
        # (Review Agent 2026-05-30 guardrail – conservative dedup only)
        # Process transfers[] first (done above). Only add from log_events if symbol has ZERO prior delta
        # from this tx's transfers[]. Wallet must be in event from/to; use tx["from_address"]/tx["to_address"]
        # for sign. ANY ambiguity, missing fields, parse error, or non-participation -> graceful skip.
        # No exceptions raised, no invented data.
        for log_event in tx.get("log_events", []) or []:
            try:
                decoded = log_event.get("decoded") or {}
                if decoded.get("name") != "Transfer":
                    continue
                params = decoded.get("params") or []
                if not isinstance(params, list):
                    continue
                param_map = {p.get("name"): p.get("value") for p in params if isinstance(p, dict) and p.get("name")}
                from_a = param_map.get("from") or param_map.get("from_address")
                to_a = param_map.get("to") or param_map.get("to_address")
                val = param_map.get("value") or param_map.get("amount")
                if not from_a or not to_a or val is None:
                    continue  # ambiguity -> skip
                w = (WALLET_ADDRESS or "").lower()
                if w not in (str(from_a).lower(), str(to_a).lower()):
                    continue
                symbol = (log_event.get("sender_contract_ticker_symbol") or
                          log_event.get("contract_ticker_symbol") or "CRO")
                if symbol in symbols_with_transfer_delta:
                    continue  # dedup guardrail: transfers[] already provided delta for this symbol in this tx
                # parse amount (defensive)
                try:
                    decimals = int(log_event.get("sender_contract_decimals") or log_event.get("contract_decimals") or 18)
                    if isinstance(val, str) and val.lower().startswith("0x"):
                        raw = int(val, 16)
                    else:
                        raw = int(val)
                    signed_amt = raw / (10 ** decimals)
                except (ValueError, TypeError, OverflowError):
                    continue  # bad data -> skip
                # sign via tx-level from/to (per guardrail)
                tx_from = (tx.get("from_address") or "").lower()
                tx_to = (tx.get("to_address") or "").lower()
                if tx_to == w:
                    delta_sign = 1
                elif tx_from == w:
                    delta_sign = -1
                else:
                    continue  # ambiguity (wallet in internal xfer but not tx signer) -> skip
                amount = abs(signed_amt * delta_sign)
                if amount == 0:
                    continue
                tx_type = "BUY" if (signed_amt * delta_sign) > 0 else "SELL"
                if symbol not in token_data:
                    token_data[symbol] = {"buys": 0, "sells": 0, "trades": []}
                if tx_type == "BUY":
                    token_data[symbol]["buys"] += amount
                else:
                    token_data[symbol]["sells"] += amount
                token_data[symbol]["trades"].append({
                    "time": tx.get("block_signed_at", "")[11:16] if tx.get("block_signed_at") else "",
                    "type": tx_type,
                    "amount": round(amount, 4),
                    "symbol": symbol
                })
            except Exception:
                continue  # any error -> graceful skip (production-safe, no crash on bad log data)

        # Basic native CRO handling (Review Agent 2026-05-30 guardrail – minimal, strictly last, _aggregate_pnl only)
        # Simple rule: if tx.get("value") > 0, treat as CRO movement using tx from/to for sign.
        # Only if "CRO" had zero prior delta from transfers[] for this tx. Skip on ANY doubt.
        try:
            val = tx.get("value")
            if val and int(val) > 0:
                w = (WALLET_ADDRESS or "").lower()
                tx_from = (tx.get("from_address") or "").lower()
                tx_to = (tx.get("to_address") or "").lower()
                if w not in (tx_from, tx_to):
                    pass  # not our tx-level movement
                elif "CRO" in symbols_with_transfer_delta:
                    pass  # transfers[] already covered native value (common case)
                else:
                    try:
                        raw = int(val)
                        amount = raw / (10 ** 18)
                        if amount <= 0:
                            pass
                        else:
                            symbol = "CRO"
                            tx_type = "BUY" if tx_to == w else "SELL"
                            if symbol not in token_data:
                                token_data[symbol] = {"buys": 0, "sells": 0, "trades": []}
                            if tx_type == "BUY":
                                token_data[symbol]["buys"] += amount
                            else:
                                token_data[symbol]["sells"] += amount
                            token_data[symbol]["trades"].append({
                                "time": tx.get("block_signed_at", "")[11:16] if tx.get("block_signed_at") else "",
                                "type": tx_type,
                                "amount": round(amount, 4),
                                "symbol": symbol
                            })
                    except (ValueError, TypeError):
                        pass  # doubt -> skip
        except Exception:
            pass  # fully defensive

    result = []
    for symbol, data in token_data.items():
        net = data["buys"] - data["sells"]
        result.append({
            "symbol": symbol,
            "trades": len(data["trades"]),
            "net": round(net, 4),
            "trades_list": data["trades"]
        })

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "tokens": result
    }


# -------------------------------------------------------------------
# Async-safe Etherscan V2 layer for production /daily_pnl (chainid=25).
# Fetches txlist (native CRO) + tokentx (ERC-20), normalizes to Covalent-like shape.
# Original sync get_today_transactions / calculate_daily_pnl kept UNCHANGED (byte-for-byte)
# for compatibility with telegram/handlers.py (out of scope / legacy protection).
# All normalization here only; _aggregate_pnl and get_daily_pnl_report untouched.
# Pagination/early-exit/partial/error handling replicated exactly from prior Covalent async.
# (Review Agent 2026-06-03 guardrails)
# -------------------------------------------------------------------

def _normalize_etherscan_item(item: Dict, action: str) -> Dict | None:
    """Tiny private helper: build *exact* synthetic Covalent-shaped item from Etherscan V2 result.
    Called ONLY from get_today_transactions_async (never from _aggregate_pnl, never from legacy).
    - txlist -> native CRO movement (only if value>0)
    - tokentx -> ERC-20 transfer
    Shape guarantees for _aggregate_pnl guardrails (transfers-first, successful, native value, log_events=[]):
      block_signed_at (ISO UTC Z from unix timeStamp), successful (isError=='0'),
      transfers=[{contract_ticker_symbol, contract_decimals, delta (signed int)}],
      from_address, to_address, value, log_events=[] .
    All adaptation/normalization confined here per Review Agent 2026-06-03 critical guardrail #1.
    """
    w = (WALLET_ADDRESS or "").lower()
    try:
        ts = int(item.get("timeStamp", 0) or 0)
    except (ValueError, TypeError):
        return None
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    block_signed_at = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    is_err = str(item.get("isError", "0"))
    successful = (is_err == "0")
    from_a = item.get("from", "") or ""
    to_a = item.get("to", "") or ""
    raw_value = item.get("value", "0") or "0"

    if action == "tokentx":
        symbol = item.get("tokenSymbol") or "???"
        try:
            decimals = int(item.get("tokenDecimal", 18))
        except (ValueError, TypeError):
            decimals = 18
        try:
            raw = int(raw_value)
        except (ValueError, TypeError):
            raw = 0
        delta = raw if to_a.lower() == w else -raw
        transfers = [{
            "contract_ticker_symbol": symbol,
            "contract_decimals": decimals,
            "delta": delta,
        }]
        val = "0"
    else:
        # txlist: native CRO only when value moves for our wallet
        symbol = "CRO"
        decimals = 18
        try:
            raw = int(raw_value)
        except (ValueError, TypeError):
            raw = 0
        if raw == 0:
            return None  # no pnl impact from this txlist entry (token side covered by tokentx)
        delta = raw if to_a.lower() == w else -raw
        transfers = [{
            "contract_ticker_symbol": symbol,
            "contract_decimals": decimals,
            "delta": delta,
        }]
        val = raw_value

    return {
        "block_signed_at": block_signed_at,
        "successful": successful,
        "from_address": from_a,
        "to_address": to_a,
        "value": val,
        "transfers": transfers,
        "log_events": [],
    }


async def get_today_transactions_async() -> List[Dict]:
    """Async-safe fetch of today's transactions using Etherscan V2 (chainid=25 via txlist + tokentx).
    Preferred for FastAPI/webhook/async contexts. Follows patterns from
    worker.py, core/wallet.py, core/dexscreener.py (async httpx, defensive).

    Pagination: page=1..5, offset=1000, sort=desc (newest-first), hard cap ~5 pages per endpoint.
    Early break on first tx older than today (using timeStamp -> UTC date).
    Per-page error or non-OK: log + break returning partial results collected (never fails whole report).
    Normalization to Covalent tx shape happens ONLY inside this fetcher + tiny _normalize helper.
    Exact defensive pagination/early-exit/partial-results/logging pattern replicated from prior async Covalent impl.
    Sync legacy path (Covalent) untouched. Output: List[Dict] synthetics for _aggregate_pnl.
    (Review Agent 2026-06-03 guardrails + UTC date per 2026-05-28)
    """
    if not WALLET_ADDRESS:
        logging.error("[ERROR] Missing WALLET_ADDRESS")
        return []

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")  # UTC for tx date filter (minimal targeted fix approved by Review Agent 2026-05-28)
    collected: List[Dict] = []
    base_url = "https://api.cronoscan.com/v2/api"  # CronoScan (Etherscan-powered for Cronos) V2; api.etherscan.io/v2 does not support chainid=25

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            for action in ("txlist", "tokentx"):
                for page in range(1, 6):  # page 1 to 5, offset=1000 per approved plan + Etherscan V2 spec
                    url = (
                        f"{base_url}?chainid=25&module=account&action={action}"
                        f"&address={WALLET_ADDRESS}&startblock=0&endblock=99999999"
                        f"&page={page}&offset=1000&sort=desc&apikey={ETHERSCAN_API_KEY}"
                    )
                    try:
                        r = await client.get(url)
                        if r.status_code != 200:
                            logging.error(f"[ERROR] Etherscan V2 {action} status {r.status_code} on page {page}")
                            break  # defensive partial results
                        data = r.json()
                        if data.get("status") != "1":
                            logging.error(f"[ERROR] Etherscan V2 {action} page {page}: {data.get('message', 'error')}")
                            break  # rate limit / invalid / partial ok
                        items = data.get("result", []) or []
                        if not items:
                            logging.info(f"Async Etherscan V2 {action} pagination: empty page {page}, stopping")
                            break
                        page_added = 0
                        hit_older = False
                        for item in items:
                            try:
                                ts = int(item.get("timeStamp", 0) or 0)
                                tx_date = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                            except Exception:
                                continue
                            if tx_date == today:
                                synth = _normalize_etherscan_item(item, action)
                                if synth:
                                    collected.append(synth)
                                    page_added += 1
                            else:
                                # older tx encountered (newest-first ordering)
                                hit_older = True
                                logging.info(f"Async Etherscan V2 {action} pagination early-exit on page {page}: encountered tx older than {today} (reason: time boundary)")
                                break  # remaining items + later pages are older
                        logging.info(f"Async Etherscan V2 {action} pagination: page {page} added {page_added} today's tx (total collected: {len(collected)})")
                        if hit_older:
                            break  # early break per guardrail
                    except Exception as page_err:
                        logging.error(f"[ERROR] Etherscan V2 {action} async pagination page {page} failed: {str(page_err)} - returning partial results")
                        break  # do not fail whole report
        logging.info(f"Async Etherscan V2 pagination complete: {len(collected)} tx for {today} (up to 5 pages per endpoint)")
        return collected
    except Exception as e:
        logging.error(f"[ERROR] Etherscan V2 async fetch: {str(e)}")
    return collected


async def calculate_daily_pnl_async() -> Dict:
    """Async version of daily PnL calculation. Reuses _aggregate_pnl."""
    transactions = await get_today_transactions_async()
    return _aggregate_pnl(transactions)


# -------------------------------------------------------------------
# Public async entrypoint for production /daily_pnl (webhook path in app/main.py)
# -------------------------------------------------------------------
async def get_daily_pnl_report() -> str:
    """Generate daily PnL report with optional Grok AI enhancement + reliable fallback.

    Flow:
    - Fetch via async Covalent layer (preferred data source per GROK_COORDINATION).
    - If no meaningful txs: clean message.
    - Attempt Grok via core.grok_client.call_grok with HARD TIMEOUT (addresses prior High review feedback on timeout control).
    - Use compact prompt from prompts/grok_daily_pnl.txt + summarized data.
    - On success/good content: return base report + Grok insights.
    - On any failure (timeout, API error, low quality): clean fallback using format_pnl_report() style.
    - Never degrades UX below previous fallback quality.
    - Does not block event loop.

    LIMITATIONS (honest, per task scope and GROK_COORDINATION.md PnL priority):
    - This is NET DELTA ONLY (buys - sells per token for the day). NOT true realized USD PnL.
    - No cost basis, no entry/exit price tracking, no USD valuation of the deltas.
    - Covalent used here (consistency with Explorer used in balances/wallet paths is future refactor).
    - Full EOD scheduling / persistence / advanced cost basis out of scope for this small increment.
    """
    # Initial fetch (async safe)
    try:
        data = await calculate_daily_pnl_async()
    except Exception as e:
        logging.exception("daily_pnl_async fetch error")
        return "Error fetching daily transactions. Please try again later."

    # No data case (clean, no Grok needed)
    if "error" in data or not data.get("tokens"):
        return "📊 No meaningful transactions found today for PnL analysis."

    # Always produce the reliable base report (fallback quality floor)
    base_report = format_pnl_report(data)

    # Try Grok enhancement (with hard timeout for responsiveness/safety)
    try:
        # Build richer context for new prompt (post-Review Agent 2026-05-28, clarification #1):
        # total_trades, active_token_count, top_movers_summary (pre-computed in Python).
        # Old daily_summary removed (new prompt uses structured movers only; Grok forbidden from numbers).
        tokens = data.get("tokens", [])
        total_trades = sum(t.get("trades", 0) for t in tokens)
        active_token_count = len(tokens)
        sorted_movers = sorted(tokens, key=lambda t: abs(t.get("net", 0)), reverse=True)[:5]
        top_movers_lines = [
            f"- {m['symbol']}: net {m['net']:+.4f} ({m['trades']} trades)"
            for m in sorted_movers
        ]
        top_movers_summary = "\n".join(top_movers_lines) if top_movers_lines else "No activity."

        prompt = load_prompt(
            "grok_daily_pnl.txt",
            date=data.get("date", "today"),
            wallet_preview=f"{WALLET_ADDRESS[:6]}...{WALLET_ADDRESS[-4:]}" if WALLET_ADDRESS else "unknown",
            total_trades=total_trades,
            active_token_count=active_token_count,
            top_movers_summary=top_movers_summary
        )

        # Hard timeout (25s) for this command path - per Review Agent feedback
        # (shorter than default to keep webhook responsive; failures always fallback)
        insight = await call_grok(prompt, timeout=25.0)

        # Quality gate: must be non-error, substantial content
        if (insight and
            not insight.startswith(("Grok API error", "Error calling Grok", "[ERROR]", "GROK_API_KEY")) and
            len(insight.strip()) > 15):
            # Use the improved formatter for the production webhook path only.
            # Old format_pnl_report() remains untouched for telegram/handlers.py compatibility.
            # (Review Agent clarification #3 - legacy sync path protection; Option A)
            return format_daily_pnl_report(data, insight.strip())
        else:
            # Low quality or empty -> silent fallback (user sees base report)
            logging.info("Grok daily PnL insight low-quality or failed; using fallback")
            return base_report + "\n\n(Grok insight unavailable this time - basic report shown)"

    except Exception as e:
        logging.exception(f"Grok daily PnL call failed (safe fallback): {e}")
        # Explicit safe fallback - never worse than pre-increment
        return base_report + "\n\n(Grok temporarily unavailable - basic report shown)"


