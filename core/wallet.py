import os
import time
import logging
from datetime import datetime, timezone

import httpx

# ---------------------------------------------------------------------------
# Cronos Explorer API v1 (live, keyed)
#
# The legacy keyless feed (cronos.org/explorer/api) silently froze for this
# wallet on 2026-05-22 while still answering "200 OK", so the bot kept reporting
# "no activity" while real trades happened (e.g. the 20-Jun-2026 swap at block
# 78249223). We now use the live, keyed Cronos Developer API and add a freshness
# guard so silent staleness can never hide again.
#
#   base : https://explorer-api.cronos.org/mainnet/api/v1
#   auth : every request needs ?apikey=<CRONOS_EXPLORER_API_KEY>
#   txns : account/getTxsByAddress            (normal transactions)
#   token: account/getCRC20TransferByAddress  (CRC-20 transfer events)
#   nativ: account/getBalance                 -> result.balance       (wei)
#   tbal : token/getAccountBalanceByContract  -> result.tokenBalance  (raw)
#   tip  : independent RPC eth_blockNumber     (live chain height)
#
# Response shape differs from Etherscan/BlockScout: from/to are
# {address, isContract} objects, fields are transactionHash/timestamp(unix),
# token symbol+decimals live in tokenMetadata, pagination uses
# pagination.session (20 rows/page).
# ---------------------------------------------------------------------------

EXPLORER_BASE = "https://explorer-api.cronos.org/mainnet/api/v1"

# Alert when the newest wallet block is more than this many blocks behind the
# live chain tip. Cronos runs ~0.45 s/block, so ~200k blocks ~= 1 day. Override
# with CRONOS_STALE_BLOCK_THRESHOLD if block time changes.
STALE_BLOCKS_THRESHOLD = int(os.getenv("CRONOS_STALE_BLOCK_THRESHOLD", "200000"))
_APPROX_BLOCK_SECONDS = 0.45


def _explorer_key():
    return os.getenv("CRONOS_EXPLORER_API_KEY")


def _to_int(x, default=0):
    try:
        return int(x)
    except (ValueError, TypeError):
        return default


def _addr(v):
    """from/to come back as {'address':.., 'isContract':..} on the new API (or a bare string)."""
    if isinstance(v, dict):
        return v.get("address") or ""
    return v or ""


async def explorer_get(client, path, params=None, full=False):
    """GET {EXPLORER_BASE}/{path} with the API key. Returns the 'result' payload
    (or the full envelope when full=True), or None on any failure. Never raises;
    logs the reason so auth/staleness problems are visible instead of silent."""
    key = _explorer_key()
    if not key:
        logging.error("[explorer] CRONOS_EXPLORER_API_KEY is not set")
        return None
    p = dict(params or {})
    p["apikey"] = key
    try:
        r = await client.get(f"{EXPLORER_BASE}/{path}", params=p)
        if r.status_code != 200:
            logging.error(f"[explorer] {path} HTTP {r.status_code}")
            return None
        data = r.json()
        if str(data.get("status")) != "1":
            logging.warning(f"[explorer] {path} status={data.get('status')} message={data.get('message')}")
            return None
        return data if full else data.get("result")
    except Exception as e:
        logging.error(f"[explorer] {path} request failed: {e}")
        return None


async def get_chain_height(client):
    """Live chain tip from the independent Cronos RPC, so we can detect the
    explorer lagging the real chain (the explorer's own height would freeze with it)."""
    rpc = os.getenv("CRONOS_RPC_URL")
    if not rpc:
        return None
    try:
        r = await client.post(
            rpc,
            json={"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1},
            timeout=15.0,
        )
        return int(r.json()["result"], 16)
    except Exception as e:
        logging.error(f"[freshness] chain-height lookup failed: {e}")
        return None


def build_stale_alert(blocks_behind, days_behind):
    return (
        f"⚠️ *Cronos data source looks stale* — the explorer feed is ~{days_behind:.1f} "
        f"day(s) / {blocks_behind:,} blocks behind the live chain. It may have frozen or "
        f"moved; wallet balances/PnL could be incomplete until it recovers. Please check it."
    )


async def send_telegram_alert(text, client=None):
    """Defensive system-alert send (mirrors worker.send_telegram). Never raises."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        logging.warning("[alert] Telegram not configured; cannot send freshness alert")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        if client is not None:
            await client.post(url, json=payload, timeout=15.0)
        else:
            async with httpx.AsyncClient(timeout=15.0) as c:
                await c.post(url, json=payload)
        return True
    except Exception as e:
        logging.error(f"[alert] Telegram send failed: {e}")
        return False


async def _explorer_block_number(client):
    """The explorer's OWN view of the chain tip (ethproxy/getBlockNumber). That
    endpoint uses a JSON-RPC-style envelope ({"result":"0x.."}), so we read it
    directly rather than via explorer_get (which expects the status=1 envelope).
    Returns int or None."""
    key = _explorer_key()
    if not key:
        return None
    try:
        r = await client.get(f"{EXPLORER_BASE}/ethproxy/getBlockNumber", params={"apikey": key})
        if r.status_code != 200:
            return None
        raw = r.json().get("result")
        if isinstance(raw, str):
            return int(raw, 16) if raw.lower().startswith("0x") else int(raw)
        if isinstance(raw, int):
            return raw
    except Exception as e:
        logging.error(f"[freshness] explorer tip lookup failed: {e}")
    return None


async def check_data_freshness(client, send_alert=True):
    """Detect whether the explorer DATA SOURCE is lagging the live chain — the exact
    failure mode that hid the 2026-05-22 freeze. Compares the explorer's own reported
    tip (ethproxy/getBlockNumber) against the INDEPENDENT Cronos RPC tip. If the
    explorer is far behind, log a warning and (by default) fire a Telegram alert
    instead of letting the bot silently report "no activity".

    This checks the SOURCE, not wallet activity, so it does NOT false-alarm when you
    simply have not traded recently. Returns a dict (handy for tests and callers)."""
    rpc_tip = await get_chain_height(client)             # independent truth
    explorer_tip = await _explorer_block_number(client)  # the source's own view
    out = {
        "rpc_tip": rpc_tip,
        "explorer_tip": explorer_tip,
        "blocks_behind": None,
        "days_behind": None,
        "stale": False,
        "alerted": False,
    }
    if not rpc_tip or not explorer_tip:
        return out
    blocks_behind = max(0, rpc_tip - explorer_tip)
    days_behind = (blocks_behind * _APPROX_BLOCK_SECONDS) / 86400.0
    out["blocks_behind"] = blocks_behind
    out["days_behind"] = days_behind
    if blocks_behind > STALE_BLOCKS_THRESHOLD:
        out["stale"] = True
        msg = build_stale_alert(blocks_behind, days_behind)
        logging.warning(f"[freshness] STALE DATA SOURCE: {msg}")
        if send_alert:
            out["alerted"] = await send_telegram_alert(msg, client)
    return out


async def get_wallet_balances(wallet_address: str):
    """Native CRO + CRC-20 token balances.
    Returns {"cro": float, "tokens": {symbol: amount}} (shape unchanged for callers).

    Balances are read from the explorer's authoritative balance endpoints
    (account/getBalance + token/getAccountBalanceByContract) — true current
    balances, not a fragile transfer-sum. Robust to bad/empty responses."""
    if not wallet_address:
        return {"cro": 0.0, "tokens": {}}

    async with httpx.AsyncClient(timeout=25.0) as client:
        # --- native CRO ---
        cro = 0.0
        bal = await explorer_get(client, "account/getBalance", {"address": wallet_address})
        if isinstance(bal, dict):
            cro = _to_int(bal.get("balance"), 0) / 10**18

        # --- distinct CRC-20 tokens seen in recent transfers (drives per-contract balance) ---
        tokens = {}
        newest_block = None
        seen = {}  # contract -> (symbol, decimals)
        rows = await explorer_get(
            client,
            "account/getCRC20TransferByAddress",
            {"address": wallet_address, "startBlock": 0, "endBlock": 99999999},
        ) or []
        for tx in rows:
            meta = tx.get("tokenMetadata") or {}
            contract = (meta.get("tokenAddress") or "").lower()
            if contract and contract not in seen:
                seen[contract] = (meta.get("tokenSymbol") or "???", _to_int(meta.get("decimals"), 18))
            b = _to_int(tx.get("blockNumber"))
            if b:
                newest_block = b if newest_block is None else max(newest_block, b)

        # --- authoritative current balance per held token ---
        for contract, (symbol, decimals) in seen.items():
            res = await explorer_get(
                client,
                "token/getAccountBalanceByContract",
                {"address": wallet_address, "contractAddress": contract},
            )
            if isinstance(res, dict):
                raw = _to_int(res.get("tokenBalance"), 0)
                if raw > 0:
                    tokens[symbol] = tokens.get(symbol, 0.0) + raw / (10 ** decimals)

        # --- freshness guard: warn if the DATA SOURCE is lagging (not wallet inactivity) ---
        try:
            await check_data_freshness(client)
        except Exception:
            pass

        return {"cro": cro, "tokens": tokens}


async def get_recent_transactions(wallet_address: str, limit: int = 20) -> list[str]:
    """Compact recent-activity strings for /grok-analyze context. Native + CRC-20,
    newest first. Partial results on any error (never raises). Do NOT use for PnL."""
    if not wallet_address:
        return []
    w = wallet_address.lower()
    collected: list[tuple[int, str]] = []

    async with httpx.AsyncClient(timeout=20.0) as client:
        # native CRO moves
        rows = await explorer_get(
            client,
            "account/getTxsByAddress",
            {"address": wallet_address, "startBlock": 0, "endBlock": 99999999},
        ) or []
        for it in rows[:limit]:
            ts = _to_int(it.get("timestamp"))
            val = _to_int(it.get("value")) / 10**18
            if val <= 0:
                continue
            ttyp = "SEND" if _addr(it.get("from")).lower() == w else "RECEIVE"
            h = (it.get("transactionHash") or "")[:8]
            tstr = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%m-%d %H:%M") if ts else "--"
            collected.append((ts, f"{tstr} | {ttyp} {val:.4f} CRO {h}..."))

        # CRC-20 token moves
        rows = await explorer_get(
            client,
            "account/getCRC20TransferByAddress",
            {"address": wallet_address, "startBlock": 0, "endBlock": 99999999},
        ) or []
        for it in rows[:limit]:
            meta = it.get("tokenMetadata") or {}
            sym = meta.get("tokenSymbol") or "???"
            dec = _to_int(meta.get("decimals"), 18)
            ts = _to_int(it.get("timestamp"))
            val = _to_int(it.get("value")) / (10 ** dec)
            if val <= 0:
                continue
            ttyp = "BUY" if _addr(it.get("to")).lower() == w else "SELL"
            h = (it.get("transactionHash") or "")[:8]
            tstr = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%m-%d %H:%M") if ts else "--"
            collected.append((ts, f"{tstr} | {ttyp} {val:.4f} {sym} {h}..."))

    collected.sort(key=lambda x: x[0], reverse=True)
    seen_s, result = set(), []
    for _, desc in collected:
        if desc not in seen_s:
            seen_s.add(desc)
            result.append(desc)
            if len(result) >= limit:
                break
    return result
