import httpx
import logging
from datetime import datetime, timezone

async def get_wallet_balances(wallet_address: str):
    """Core wallet balance logic - robust to bad/empty responses."""
    if not wallet_address:
        return {"cro": 0.0, "tokens": {}}

    async with httpx.AsyncClient(timeout=20.0) as client:
        cro = 0.0
        try:
            native_resp = await client.get(
                f"https://cronos.org/explorer/api?module=account&action=balance&address={wallet_address}"
            )
            if native_resp.status_code == 200:
                result = native_resp.json().get("result", "0")
                if result:
                    cro = int(result) / 10**18
        except Exception:
            pass

        tokens = {}
        try:
            token_resp = await client.get(
                f"https://cronos.org/explorer/api?module=account&action=tokentx&address={wallet_address}&page=1&offset=200&sort=desc"
            )
            if token_resp.status_code == 200:
                txs = token_resp.json().get("result", []) or []
                for tx in txs:
                    symbol = tx.get("tokenSymbol", "???")
                    decimals = int(tx.get("tokenDecimal", 18))
                    value = int(tx.get("value", 0) or 0) / (10 ** decimals)
                    if value > 0:
                        tokens[symbol] = tokens.get(symbol, 0) + value
        except Exception:
            pass

        return {"cro": cro, "tokens": tokens}


async def get_recent_transactions(wallet_address: str, limit: int = 20) -> list[str]:
    """Minimal defensive helper to support live /grok-analyze (Review Agent 2026-06-04).
    Uses only cronos.org/explorer/api (consistent with get_wallet_balances; no ETHERSCAN key).
    Fetches txlist (native) + tokentx (ERC20), merges by timestamp (newest first), returns
    up to `limit` compact "MM-DD HH:MM | TYPE amt SYMBOL short-hash" strings.
    Partial results on any error (never raises). Silent fail per existing core/wallet style.
    Do NOT use for PnL or modify /daily_pnl -- this is isolated for Grok context.
    """
    # Review Agent 2026-06-04: minimal, defensive, explorer-only, returns partial on error
    if not wallet_address:
        return []
    w = wallet_address.lower()
    collected: list[tuple[int, str]] = []

    async with httpx.AsyncClient(timeout=20.0) as client:
        # Native txlist (CRO value moves)
        try:
            url = (
                f"https://cronos.org/explorer/api?module=account&action=txlist"
                f"&address={wallet_address}&page=1&offset=20&sort=desc"
            )
            r = await client.get(url)
            if r.status_code == 200:
                for item in (r.json().get("result") or [])[:20]:
                    try:
                        ts = int(item.get("timeStamp") or 0)
                        val = int(item.get("value") or 0) / 10**18
                        if val <= 0:
                            continue
                        frm = (item.get("from") or "").lower()
                        ttyp = "SEND" if frm == w else "RECEIVE"
                        h = (item.get("hash") or "")[:8]
                        tstr = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%m-%d %H:%M")
                        collected.append((ts, f"{tstr} | {ttyp} {val:.4f} CRO {h}..."))
                    except Exception:
                        continue
        except Exception:
            pass  # partial results only

        # Token transfers
        try:
            url = (
                f"https://cronos.org/explorer/api?module=account&action=tokentx"
                f"&address={wallet_address}&page=1&offset=20&sort=desc"
            )
            r = await client.get(url)
            if r.status_code == 200:
                for item in (r.json().get("result") or [])[:20]:
                    try:
                        ts = int(item.get("timeStamp") or 0)
                        sym = item.get("tokenSymbol") or "???"
                        dec = int(item.get("tokenDecimal") or 18)
                        val = int(item.get("value") or 0) / (10 ** dec)
                        if val <= 0:
                            continue
                        to = (item.get("to") or "").lower()
                        ttyp = "BUY" if to == w else "SELL"
                        h = (item.get("hash") or "")[:8]
                        tstr = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%m-%d %H:%M")
                        collected.append((ts, f"{tstr} | {ttyp} {val:.4f} {sym} {h}..."))
                    except Exception:
                        continue
        except Exception:
            pass  # partial results only

    # Newest first, dedup by desc, limit
    collected.sort(key=lambda x: x[0], reverse=True)
    seen: set[str] = set()
    result: list[str] = []
    for _, desc in collected:
        if desc not in seen:
            seen.add(desc)
            result.append(desc)
            if len(result) >= limit:
                break
    return result
