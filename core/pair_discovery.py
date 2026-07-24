"""Multi-chain new-pair discovery via GeckoTerminal (2026-07-23).

Replaces the broken Dexscreener `search?q=cronos` feed (which returned
established pairs ranked by relevance, not new ones — 0 passed the newness
filter). GeckoTerminal's `new_pools` endpoint returns pools created in the past
~48h, keyless, 30 calls/min, on Cronos / Solana / Sui.

  GET https://api.geckoterminal.com/api/v2/networks/{network}/new_pools
      ?include=base_token,quote_token,dex

Pure parsing/classification here (unit-tested offline); async fetch is defensive
(429 backoff, never raises). The 0-100 scoring math in worker.score_pair is
UNCHANGED — parse_gt_pool maps GeckoTerminal fields into the exact
{volume.h1, txns.h1.buys/sells, priceChange.h1} shape score_pair already reads.

NOTE: this is discovery only. The Dexscreener token-pricing used by /wallet is a
different endpoint and is deliberately left untouched.
"""

import asyncio
import logging
import math
import os
from datetime import datetime, timezone

GECKOTERMINAL_BASE = "https://api.geckoterminal.com/api/v2"
_UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

# Confirmed network ids (2026-07-22).
DEFAULT_CHAINS = "cro,solana,sui-network"
# Per-chain liquidity floors: Solana is a firehose of junk launches, Cronos is
# nearly barren, so the floors differ. Env override: PAIR_MIN_LIQUIDITY_USD_{CHAIN}.
_DEFAULT_MIN_LIQ = {"cro": 5000.0, "solana": 10000.0, "sui-network": 10000.0}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        v = float(raw)
        return v if math.isfinite(v) and v >= 0 else default
    except (TypeError, ValueError):
        return default


def _chain_env_suffix(chain: str) -> str:
    """cro -> CRO, sui-network -> SUI_NETWORK (env-var-safe upper)."""
    return chain.upper().replace("-", "_")


def chains_enabled() -> list:
    raw = os.getenv("CHAINS_ENABLED", DEFAULT_CHAINS)
    return [c.strip() for c in raw.split(",") if c.strip()]


def min_liquidity_for(chain: str) -> float:
    return _env_float(f"PAIR_MIN_LIQUIDITY_USD_{_chain_env_suffix(chain)}",
                      _DEFAULT_MIN_LIQ.get(chain, 10000.0))


def min_score_for(chain: str, global_default: float) -> float:
    return _env_float(f"PAIR_MIN_SCORE_{_chain_env_suffix(chain)}", global_default)


def _f(x, default=0.0):
    try:
        v = float(x)
        return v if math.isfinite(v) else default
    except (TypeError, ValueError):
        return default


def _token_symbol_addr(token_id, included_by_id):
    """Resolve a token's (symbol, address) from the JSON:API included[] block,
    falling back to the '{network}_{address}' id when the token isn't included."""
    inc = included_by_id.get(token_id) if token_id else None
    if isinstance(inc, dict):
        a = inc.get("attributes") or {}
        addr = (a.get("address") or "").strip()
        sym = (a.get("symbol") or "").strip()
        if addr or sym:
            return sym or "?", addr
    # fallback: id looks like "cro_0x..." / "solana_ABC" / "sui-network_0x..."
    if isinstance(token_id, str) and "_" in token_id:
        return "?", token_id.split("_", 1)[1]
    return "?", ""


def parse_gt_pool(pool: dict, network: str, included_by_id: dict) -> dict | None:
    """Normalize one GeckoTerminal pool into the shape the rest of the worker
    uses. Returns None if it lacks an address (unusable). Pure; never raises.

    The returned dict is BOTH the alert/paper metadata AND a score_pair-ready
    payload (volume.h1 / txns.h1 / priceChange.h1), so scoring math is unchanged.
    """
    if not isinstance(pool, dict):
        return None
    attrs = pool.get("attributes") if isinstance(pool.get("attributes"), dict) else {}
    rels = pool.get("relationships") if isinstance(pool.get("relationships"), dict) else {}
    address = (attrs.get("address") or "").strip()
    if not address:
        return None

    def _rel_id(name):
        d = (rels.get(name) or {}).get("data") if isinstance(rels.get(name), dict) else None
        return d.get("id") if isinstance(d, dict) else None

    base_sym, base_addr = _token_symbol_addr(_rel_id("base_token"), included_by_id)
    quote_sym, _ = _token_symbol_addr(_rel_id("quote_token"), included_by_id)
    dex = _rel_id("dex") or "?"

    # name like "WOOF / WCRO" is a good symbol fallback
    name = (attrs.get("name") or "").strip()
    if base_sym == "?" and " / " in name:
        base_sym = name.split(" / ", 1)[0].strip() or "?"
    if quote_sym == "?" and " / " in name:
        quote_sym = name.split(" / ", 1)[1].strip() or "?"

    vol = attrs.get("volume_usd") if isinstance(attrs.get("volume_usd"), dict) else {}
    pc = attrs.get("price_change_percentage") if isinstance(attrs.get("price_change_percentage"), dict) else {}
    tx = attrs.get("transactions") if isinstance(attrs.get("transactions"), dict) else {}
    tx1h = tx.get("h1") if isinstance(tx.get("h1"), dict) else {}
    try:
        buys = int(tx1h.get("buys") or 0)
        sells = int(tx1h.get("sells") or 0)
    except (TypeError, ValueError):
        buys = sells = 0

    return {
        "chain": network,
        "dex": dex,
        "pairAddress": address,
        "key": f"{network}:{address.lower()}",
        "name": name or f"{base_sym} / {quote_sym}",
        "baseToken": {"symbol": base_sym or "?", "address": base_addr},
        "quoteToken": {"symbol": quote_sym or "?"},
        "priceUsd": attrs.get("base_token_price_usd"),
        "url": f"https://www.geckoterminal.com/{network}/pools/{address}",
        "liquidity_usd": _f(attrs.get("reserve_in_usd")),
        "fdv_usd": _f(attrs.get("fdv_usd")),
        "created_at": attrs.get("pool_created_at"),
        # --- score_pair-ready sub-dicts (scoring math untouched) ---
        "volume": {"h1": _f(vol.get("h1"))},
        "txns": {"h1": {"buys": buys, "sells": sells}},
        "priceChange": {"h1": _f(pc.get("h1"))},
    }


def pool_age_hours(created_at, now_utc) -> float | None:
    """Age in hours from an ISO8601 pool_created_at, or None if unparseable."""
    if not created_at:
        return None
    try:
        s = str(created_at).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (now_utc - dt).total_seconds() / 3600.0
    except (TypeError, ValueError):
        return None


def classify_pool(created_at, now_utc, min_age_minutes: float,
                  newness_window_hours: float) -> str:
    """Pure maturity rule. Returns:
      'pending'  — younger than min_age_minutes (no vol/tx history yet; hold, do
                   NOT score or discard — scoring it now would score ~0)
      'mature'   — old enough to score AND still within the newness window
      'expired'  — older than the newness window (no longer a NEW pair)
      'unknown'  — created_at unparseable (treat as expired: never score blind)
    """
    age_h = pool_age_hours(created_at, now_utc)
    if age_h is None:
        return "unknown"
    if age_h < 0:
        return "pending"  # clock skew: treat a "future" pool as not-yet-ready
    if age_h < (min_age_minutes / 60.0):
        return "pending"
    if age_h > newness_window_hours:
        return "expired"
    return "mature"


def parse_pool_prices(body: dict) -> dict:
    """Map a GeckoTerminal pools/multi response to {pool_address: price_usd},
    keyed by BOTH the original and the lowercased address. Base58 Solana
    addresses are case-sensitive while EVM/Sui hex are not — keying both makes
    the position lookup robust regardless of how the address was stored. Pure;
    skips pools with no usable positive price. Never raises."""
    out = {}
    for pool in ((body or {}).get("data") or []):
        a = pool.get("attributes") if isinstance(pool, dict) else None
        if not isinstance(a, dict):
            continue
        addr = (a.get("address") or "").strip()
        if not addr:
            continue
        try:
            p = float(a.get("base_token_price_usd"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(p) or p <= 0:
            continue
        out[addr] = p
        out[addr.lower()] = p
    return out


async def fetch_pool_prices(client, network: str, addresses: list,
                            max_retries: int = 3) -> dict:
    """Current base-token USD price per pool via pools/multi (up to 50 addresses
    per call), for one chain. Returns {address: price} (both cases). Exponential
    429 backoff; never raises -> partial/empty dict on failure. This is the paper
    engine's exit-pricing feed (one call per chain per cycle, never per-position).
    """
    out = {}
    addrs = [a for a in (addresses or []) if a]
    for i in range(0, len(addrs), 50):
        chunk = addrs[i:i + 50]
        url = f"{GECKOTERMINAL_BASE}/networks/{network}/pools/multi/{','.join(chunk)}"
        for attempt in range(max_retries + 1):
            try:
                r = await client.get(url, headers=_UA, timeout=20.0)
                if r.status_code == 429:
                    if attempt < max_retries:
                        await asyncio.sleep(1.0 * (2 ** attempt))
                        continue
                    logging.warning(f"[discovery] {network} pools/multi 429 after retries")
                    return out
                if r.status_code != 200:
                    logging.warning(f"[discovery] {network} pools/multi HTTP {r.status_code}")
                    break
                out.update(parse_pool_prices(r.json()))
                break
            except Exception as e:
                if attempt < max_retries:
                    await asyncio.sleep(1.0 * (2 ** attempt))
                    continue
                logging.warning(f"[discovery] {network} pools/multi failed: {type(e).__name__}")
                break
    return out


async def fetch_new_pools(client, network: str, max_retries: int = 3) -> list:
    """GET new_pools for one network. Returns a list of normalized pool dicts
    (via parse_gt_pool), or [] on any failure. Exponential backoff on HTTP 429.
    Never raises — the caller's loop must never die on a feed hiccup."""
    url = f"{GECKOTERMINAL_BASE}/networks/{network}/new_pools"
    params = {"include": "base_token,quote_token,dex"}
    for attempt in range(max_retries + 1):
        try:
            r = await client.get(url, params=params, headers=_UA, timeout=20.0)
            if r.status_code == 429:
                if attempt < max_retries:
                    await asyncio.sleep(1.0 * (2 ** attempt))  # 1s,2s,4s
                    continue
                logging.warning(f"[discovery] {network} 429 after {max_retries} retries")
                return []
            if r.status_code != 200:
                logging.warning(f"[discovery] {network} HTTP {r.status_code}")
                return []
            body = r.json()
            included_by_id = {}
            for inc in (body.get("included") or []):
                if isinstance(inc, dict) and inc.get("id"):
                    included_by_id[inc["id"]] = inc
            out = []
            for pool in (body.get("data") or []):
                norm = parse_gt_pool(pool, network, included_by_id)
                if norm:
                    out.append(norm)
            return out
        except Exception as e:
            if attempt < max_retries:
                await asyncio.sleep(1.0 * (2 ** attempt))
                continue
            logging.warning(f"[discovery] {network} fetch failed: {type(e).__name__}")
            return []
    return []
