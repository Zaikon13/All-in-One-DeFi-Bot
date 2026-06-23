# core/pnl_calculator.py - Simple & Working Daily PnL Calculator

import os
import logging
from datetime import datetime, timezone
from typing import List, Dict

import httpx

# Reuse Grok client (SOT for calls, prompts, quality gates - consolidated 2026-06-04)
from core.claude_client import call_grok, load_prompt, is_valid_grok_response

# Review Agent 2026-06-09: Import for Phase 1 current price enrichment (best-effort, isolated).
from core.price_service import PriceService

# Live Cronos Explorer v1 client + data-freshness guard (replaces the frozen keyless feed).
from core.wallet import explorer_get, check_data_freshness

WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")

COVALENT_BASE = "https://api.covalenthq.com/v1"


# API keys are read LAZILY (inside the functions that use them) so importing this
# module never crashes when env vars are absent (worker boot, CI smoke, fresh clone).
# Missing keys are handled defensively at call time, not raised at import time.
def _get_covalent_api_key() -> str | None:
    """Lazily read COVALENT_API_KEY (legacy sync Covalent path only)."""
    return os.getenv("COVALENT_API_KEY")


def _get_etherscan_api_key() -> str | None:
    """Lazily read ETHERSCAN_API_KEY (async production /daily_pnl path; chainid=25)."""
    return os.getenv("ETHERSCAN_API_KEY")


def get_today_transactions() -> List[Dict]:
    """Fetch today's transactions (simple & reliable)
    DEPRECATED (Review Agent 2026-06-06): Legacy sync Covalent path.
    Telegram /daily_pnl command unified to production async get_daily_pnl_report().
    This function is no longer called from production code (kept for reference only).
    """
    if not WALLET_ADDRESS:
        print("[ERROR] Missing WALLET_ADDRESS")
        return []

    covalent_api_key = _get_covalent_api_key()
    if not covalent_api_key:
        print("[ERROR] Missing COVALENT_API_KEY")
        return []

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")  # UTC for tx date filter (minimal targeted fix approved by Review Agent 2026-05-28)
    url = f"{COVALENT_BASE}/25/address/{WALLET_ADDRESS}/transactions_v3/?key={covalent_api_key}"

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
    """Calculate simple but correct daily PnL
    DEPRECATED (Review Agent 2026-06-06): Legacy sync Covalent path.
    Telegram /daily_pnl command unified to production async get_daily_pnl_report().
    This function is no longer called from production code (kept for reference only).
    format_pnl_report() is still actively used as fallback inside the production path.
    """
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

        # Review Agent 2026-06-09: Phase 1 current price enrichment display (additive, optional).
        # Only show USD fields if present (i.e., price data was successfully fetched for this token).
        if "position_value_usd" in token:
            lines.append(f"**Position Value (USD):** ${token['position_value_usd']:+.4f}")
        if "avg_cost_usd" in token:
            lines.append(f"**Avg Cost (USD):** ${token['avg_cost_usd']:.4f}")
        lines.append("")

    # Review Agent 2026-06-09: Optional total portfolio value at end (additive only).
    if "total_portfolio_value_usd" in data:
        lines.append(f"**Total Portfolio Value (USD):** ${data['total_portfolio_value_usd']:+.4f}")
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
    # Review Agent 2026-06-06: Command path unified - legacy sync path no longer
    # used for /daily_pnl in production. format_pnl_report() retained here as
    # reliable fallback base (see get_daily_pnl_report).

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

    # Review Agent 2026-06-09: Phase 1 current price enrichment display (additive and optional).
    # Only show for tokens that have price data from the enrichment layer.
    # This complements the legacy formatter and makes the new fields visible in the main report path.
    enriched = [t for t in tokens if "position_value_usd" in t]
    if enriched:
        lines.append("**Enriched Positions (USD)**")
        for t in enriched:
            lines.append(f"• {t['symbol']}: ${t['position_value_usd']:+.4f}")
            if "avg_cost_usd" in t:
                lines.append(f"  Avg Cost: ${t['avg_cost_usd']:.4f}")
        lines.append("")

    if "total_portfolio_value_usd" in data:
        lines.append(f"**Total Portfolio Value (USD):** ${data['total_portfolio_value_usd']:+.4f}")
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
    # Review Agent 2026-06-06: Legacy sync calculate_daily_pnl() + get_today_transactions()
    # deprecated after unification of telegram/handlers.py to production async path.
    # Kept for reference only (no longer called in production). Duplicate logic
    # was preserved historically for compatibility.
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
# Review Agent 2026-06-06: Telegram /daily_pnl command unified to this path
# (see telegram/handlers.py). Original sync get_today_transactions / calculate_daily_pnl
# deprecated (no longer used by production command; kept for reference).
# Legacy protection comments updated post-unification.
# All normalization here only; _aggregate_pnl and get_daily_pnl_report untouched.
# Pagination/early-exit/partial/error handling replicated exactly from prior Covalent async.
# (Review Agent 2026-06-03 guardrails + 2026-06-06 unification)
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


def _adapt_explorer_row(item: Dict, action: str) -> Dict:
    """Adapt a Cronos Explorer v1 row into the legacy Etherscan-shaped dict that
    _normalize_etherscan_item expects (timeStamp, from, to, value, isError, and for
    tokens tokenSymbol/tokenDecimal). This keeps _normalize_etherscan_item AND
    _aggregate_pnl completely untouched. New-API quirks handled here:
      - from/to are {address, isContract} objects (not bare strings)
      - fields are transactionHash / timestamp(unix) (not hash / timeStamp)
      - token symbol + decimals live in tokenMetadata
    """
    f = item.get("from")
    t = item.get("to")
    f = f.get("address") if isinstance(f, dict) else (f or "")
    t = t.get("address") if isinstance(t, dict) else (t or "")
    err = item.get("error")
    adapted = {
        "timeStamp": str(item.get("timestamp", 0) or 0),
        "from": f,
        "to": t,
        "value": str(item.get("value", "0") or "0"),
        "isError": "0" if err in (None, "", "0", "null") else "1",
        "hash": item.get("transactionHash", ""),
    }
    if action == "tokentx":
        meta = item.get("tokenMetadata") or {}
        adapted["tokenSymbol"] = meta.get("tokenSymbol") or "???"
        adapted["tokenDecimal"] = str(meta.get("decimals", 18) or 18)
    return adapted


async def get_today_transactions_async() -> List[Dict]:
    """Async-safe fetch of today's transactions from the live Cronos Explorer v1 API.

    Data source: explorer-api.cronos.org/mainnet/api/v1 (keyed), replacing the
    legacy keyless feed (cronos.org/explorer/api) that silently froze for this
    wallet on 2026-05-22. Uses account/getTxsByAddress (native CRO) +
    account/getCRC20TransferByAddress (CRC-20). Each row is adapted to the legacy
    Etherscan shape and passed to the UNCHANGED _normalize_etherscan_item ->
    _aggregate_pnl path.

    Pagination: pagination.session cursor, newest-first, capped at ~10 pages per
    endpoint; early-exit on the first tx older than today (UTC). Defensive: any
    error returns partial results (never fails the whole report).

    Freshness guard: if the newest data is far behind the live chain, log a
    warning and fire a Telegram alert instead of silently reporting "no activity".

    Output: List[Dict] synthetics for _aggregate_pnl (UTC date filter).
    """
    if not WALLET_ADDRESS:
        logging.error("[ERROR] Missing WALLET_ADDRESS")
        return []

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")  # UTC tx-date filter
    collected: List[Dict] = []
    newest_block = None
    newest_ts = None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for path, action in (
                ("account/getTxsByAddress", "txlist"),
                ("account/getCRC20TransferByAddress", "tokentx"),
            ):
                session = None
                for page in range(1, 11):  # cap ~10 pages (~200 rows) per endpoint
                    params = {"address": WALLET_ADDRESS, "startBlock": 0, "endBlock": 99999999}
                    if session:
                        params["session"] = session
                    env = await explorer_get(client, path, params, full=True)
                    if not env:
                        break  # auth/staleness/error already logged; partial results
                    items = env.get("result") or []
                    if not items:
                        break
                    page_added = 0
                    hit_older = False
                    for item in items:
                        try:
                            ts = int(item.get("timestamp", 0) or 0)
                        except (ValueError, TypeError):
                            ts = 0
                        try:
                            b = int(item.get("blockNumber", 0) or 0)
                        except (ValueError, TypeError):
                            b = 0
                        if b:
                            newest_block = b if newest_block is None else max(newest_block, b)
                        if ts and (newest_ts is None or ts > newest_ts):
                            newest_ts = ts
                        tx_date = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d") if ts else ""
                        if tx_date == today:
                            synth = _normalize_etherscan_item(_adapt_explorer_row(item, action), action)
                            if synth:
                                collected.append(synth)
                                page_added += 1
                        elif tx_date and tx_date < today:
                            hit_older = True  # newest-first: remaining rows are older
                            break
                    logging.info(f"Cronos Explorer {action}: page {page} added {page_added} today's tx (total {len(collected)})")
                    if hit_older:
                        break
                    session = (env.get("pagination") or {}).get("session")
                    if not session:
                        break
            # Freshness guard: alert if the DATA SOURCE is lagging the live chain.
            try:
                await check_data_freshness(client)
            except Exception as fe:
                logging.error(f"[freshness] check failed (non-fatal): {fe}")
        logging.info(f"Cronos Explorer fetch complete: {len(collected)} tx for {today}")
        return collected
    except Exception as e:
        logging.error(f"[ERROR] Cronos Explorer async fetch: {str(e)}")
    return collected


async def calculate_daily_pnl_async() -> Dict:
    """Async version of daily PnL calculation. Reuses _aggregate_pnl."""
    transactions = await get_today_transactions_async()
    return _aggregate_pnl(transactions)


# Review Agent 2026-06-09: Private best-effort enrichment for Phase 1.
# Implements current price valuation + simple average cost (using current price for buys in the day).
# This is additive only: new fields are added to token dicts; the original net-delta shape
# from _aggregate_pnl is never modified.
# The function must remain best-effort and non-blocking (Condition 3).
def _enrich_with_current_prices(data: dict) -> dict:
    """Best-effort enrichment with current prices (Phase 1 scope only).

    For each token that has a current price:
    - position_value_usd = current_price * net_amount
    - If the day's trades_list contains BUY trades:
        - avg_cost_usd = (sum of buy quantities valued at current price) / total bought quantity
          (simple average cost approximation; see comment below)

    New fields are stored directly in the token dicts (additive).
    A root-level total_portfolio_value_usd may also be added.

    Returns the (possibly augmented) data. On any error, returns the original data unchanged.
    """
    # Review Agent 2026-06-09: Early exit for invalid data; preserve original.
    if not data or "error" in data or not data.get("tokens"):
        return data

    try:
        # Review Agent 2026-06-09: Obtain current prices via the isolated helper (from Βήμα 2.1).
        # This call is best-effort; failure here falls through to return original data.
        service = PriceService()
        symbols = [t.get("symbol") for t in data.get("tokens", []) if t.get("symbol")]
        prices = service.get_current_prices(symbols)

        if not prices:
            service.close()
            return data

        # shallow copy of top level to avoid mutating caller's dict in some execution paths
        data = dict(data)
        enriched_tokens = []
        total_portfolio_usd = 0.0

        for token in data.get("tokens", []):
            # per-token copy so we can add fields without affecting the original list items
            token = dict(token)
            symbol = token.get("symbol")
            price = prices.get(symbol)

            if price is not None:
                net = token.get("net", 0.0)
                position_value_usd = price * net
                token["position_value_usd"] = round(position_value_usd, 4)
                token["has_price_data"] = True

                # Review Agent 2026-06-09: Simple Average Cost calculation (Phase 1 limitation).
                # We only consider BUY trades that occurred *within this day's data*.
                # Cost is approximated by valuing those buy quantities at *today's current price*.
                # This is NOT a true historical cost basis (no historical prices in Phase 1).
                # It is deliberately simple (not FIFO, not weighted by time, etc.).
                # Only tokens that actually have BUY activity in the day's trades_list will get avg_cost_usd.
                trades = token.get("trades_list", [])
                buys = [t for t in trades if t.get("type") == "BUY"]
                if buys:
                    total_bought_qty = sum(t.get("amount", 0) for t in buys)
                    if total_bought_qty > 0:
                        # Valuing the buys at the current price gives a same-day "average cost" figure.
                        total_buy_usd = total_bought_qty * price
                        avg_cost_usd = total_buy_usd / total_bought_qty
                        token["avg_cost_usd"] = round(avg_cost_usd, 4)

                total_portfolio_usd += position_value_usd

            enriched_tokens.append(token)

        data["tokens"] = enriched_tokens

        # Review Agent 2026-06-09: Optional aggregate for convenience (additive only).
        if total_portfolio_usd > 0:
            data["total_portfolio_value_usd"] = round(total_portfolio_usd, 4)

        # Keep raw prices for potential use in later phases or debugging (private key).
        data["_current_prices"] = prices

        service.close()

    except Exception as e:
        # Review Agent 2026-06-09: All errors are swallowed. Enrichment is purely optional.
        # The caller (get_daily_pnl_report) will continue with whatever data we return here,
        # which in error paths is the original (or partially copied) net-delta data.
        logging.info(f"Price enrichment (Phase 1) skipped due to error: {e}")
        return data

    return data


# -------------------------------------------------------------------
# Public async entrypoint for production /daily_pnl (webhook path in app/main.py)
# -------------------------------------------------------------------
async def get_daily_pnl_report() -> str:
    """Generate daily PnL report with optional Grok AI enhancement + reliable fallback.

    Flow:
    - Fetch via async Etherscan V2 (production path; command path unified 2026-06-06).
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
    - Data source: Etherscan V2 / CronoScan (unified across webhook and Telegram command post-2026-06-06).
    - Full EOD scheduling / persistence / advanced cost basis out of scope for this small increment.
    """
    # Initial fetch (async safe)
    try:
        data = await calculate_daily_pnl_async()
    except Exception as e:
        logging.exception("daily_pnl_async fetch error")
        return "Error fetching daily transactions. Please try again later."

    # Review Agent 2026-06-09: Best-effort current price enrichment (Phase 1).
    # This call is non-blocking. If the price helper fails or returns no data,
    # we continue unchanged with the original net-delta data for full backward compatibility.
    # The enrichment now computes position_value_usd and simple avg_cost_usd (additive fields only).
    data = _enrich_with_current_prices(data)

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

        # Quality gate: must be non-error, substantial content (now via SOT helper in core/grok_client.py)
        if is_valid_grok_response(insight):
            # Use the improved formatter for the production path (now includes unified command).
            # format_pnl_report() retained as fallback (see base_report above).
            # Review Agent 2026-06-06: telegram/handlers.py now calls this function directly.
            return format_daily_pnl_report(data, insight.strip())
        else:
            # Low quality or empty -> silent fallback (user sees base report)
            logging.info("Grok daily PnL insight low-quality or failed; using fallback")
            return base_report + "\n\n(Grok insight unavailable this time - basic report shown)"

    except Exception as e:
        logging.exception(f"Grok daily PnL call failed (safe fallback): {e}")
        # Explicit safe fallback - never worse than pre-increment
        return base_report + "\n\n(Grok temporarily unavailable - basic report shown)"


# Review Agent 2026-06-09: Phase 1 current price enrichment active (position_value_usd + simple avg_cost_usd)
# The new fields are displayed conditionally in both formatters when present in the enriched data.
# This completes the display part of Phase 1 without altering calculation logic.


