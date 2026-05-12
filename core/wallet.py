import httpx
import logging

async def get_wallet_balances(wallet_address: str):
    """Core wallet balance logic"""
    async with httpx.AsyncClient(timeout=20.0) as client:
        # CRO balance
        native_resp = await client.get(f"https://cronos.org/explorer/api?module=account&action=balance&address={wallet_address}")
        native_resp.raise_for_status()
        cro = int(native_resp.json().get('result', 0)) / 10**18

        # Tokens
        token_resp = await client.get(f"https://cronos.org/explorer/api?module=account&action=tokentx&address={wallet_address}&page=1&offset=200&sort=desc")
        token_resp.raise_for_status()
        txs = token_resp.json().get('result', [])

        tokens = {}
        for tx in txs:
            symbol = tx.get('tokenSymbol', '???')
            decimals = int(tx.get('tokenDecimal', 18))
            value = int(tx.get('value', 0)) / (10 ** decimals)
            tokens[symbol] = tokens.get(symbol, 0) + value

        return {'cro': cro, 'tokens': tokens}
