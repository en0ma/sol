"""Consistent Whirlpool + vault read through Surfpool JSON-RPC.

Reads all three accounts in one getMultipleAccounts response and validates
the pool account, vault owners, mints, liquidity and vault authorities.
No DEX APIs, quote approximations or transactions are used.
"""
import base64
import json
import os
from arb.rpc import call
from arb.orca_whirlpool import PROGRAM, decode, fetch_pool
from arb.token_vaults import TOKEN_PROGRAM, decode_token_account

def _decode(account, expected_owner):
    if not account or account.get("owner") != expected_owner or account.get("executable"):
        raise ValueError("missing account or unexpected program owner")
    payload = account.get("data")
    if not isinstance(payload, list) or len(payload) != 2 or payload[1] != "base64":
        raise ValueError("unexpected account data encoding")
    return base64.b64decode(payload[0], validate=True)

def snapshot(rpc, pool_address):
    # First identify vault addresses, then fetch a single consistent snapshot.
    seed = fetch_pool(rpc, pool_address)
    addresses = [pool_address, seed["token_vault_a"], seed["token_vault_b"]]
    if len(set(addresses)) != 3:
        raise ValueError("pool/vault addresses overlap")
    response = call(rpc, "getMultipleAccounts", [addresses, {
        "encoding": "base64", "commitment": "confirmed"
    }])
    slot = response.get("context", {}).get("slot")
    accounts = response.get("value")
    if not isinstance(slot, int) or not isinstance(accounts, list) or len(accounts) != 3:
        raise ValueError("missing snapshot slot or accounts")
    pool = decode(_decode(accounts[0], PROGRAM))
    if pool["token_vault_a"] != addresses[1] or pool["token_vault_b"] != addresses[2]:
        raise ValueError("vault addresses changed during snapshot")
    a = decode_token_account(_decode(accounts[1], TOKEN_PROGRAM))
    b = decode_token_account(_decode(accounts[2], TOKEN_PROGRAM))
    if a["mint"] != pool["token_mint_a"] or b["mint"] != pool["token_mint_b"]:
        raise ValueError("pool and token vault mint mismatch")
    if a["authority"] != b["authority"]:
        raise ValueError("different vault authorities")
    if a["amount_base_units"] == 0 or b["amount_base_units"] == 0 or int(pool["liquidity"]) == 0:
        raise ValueError("empty vault or zero active liquidity")
    return {"slot": slot, "pool_address": pool_address, "pool": pool, "vault_a": a, "vault_b": b}

if __name__ == "__main__":
    import sys
    addresses = os.environ.get("WHIRLPOOL_ADDRESSES", "").split(",")
    addresses = [a.strip() for a in addresses if a.strip()]
    if not addresses:
        print("NOT_CONFIGURED: set WHIRLPOOL_ADDRESSES to verified pool pubkeys", file=sys.stderr)
        sys.exit(2)
    print(json.dumps([snapshot(os.environ.get("SOLANA_RPC_URL", "http://127.0.0.1:8899"), a)
                      for a in addresses], indent=2))
