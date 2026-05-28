import httpx
import logging

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
