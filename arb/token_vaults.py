"""Validate SPL token vault data read from Surfpool RPC. No DEX HTTP APIs."""
import base64
from arb.rpc import call
from arb.orca_whirlpool import b58

TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
SPL_TOKEN_ACCOUNT_LEN = 165

def decode_token_account(raw):
    if len(raw) != SPL_TOKEN_ACCOUNT_LEN:
        raise ValueError("unexpected classic SPL token account length")
    state = raw[108]
    if state != 1:
        raise ValueError("vault is not an initialized token account")
    return {
        "mint": b58(raw[0:32]),
        "authority": b58(raw[32:64]),
        "amount_base_units": int.from_bytes(raw[64:72], "little"),
        "state": state,
    }

def fetch_vaults(rpc, addresses):
    if not addresses or len(addresses) != len(set(addresses)):
        raise ValueError("vault addresses must be distinct and nonempty")
    result = call(rpc, "getMultipleAccounts", [
        addresses, {"encoding": "base64", "commitment": "confirmed"}
    ])
    values = result.get("value")
    if not isinstance(values, list) or len(values) != len(addresses):
        raise ValueError("unexpected RPC response length")
    found = {}
    for address, account in zip(addresses, values):
        if not account or account.get("owner") != TOKEN_PROGRAM or account.get("executable"):
            raise ValueError("missing or incorrectly owned classic SPL vault: " + address)
        payload = account.get("data")
        if not isinstance(payload, list) or len(payload) != 2 or payload[1] != "base64":
            raise ValueError("invalid token account encoding")
        state = decode_token_account(base64.b64decode(payload[0], validate=True))
        found[address] = state
    return found

def verify_whirlpool_vaults(rpc, pool):
    vault_a, vault_b = pool["token_vault_a"], pool["token_vault_b"]
    accounts = fetch_vaults(rpc, [vault_a, vault_b])
    a, b = accounts[vault_a], accounts[vault_b]
    if a["mint"] != pool["token_mint_a"] or b["mint"] != pool["token_mint_b"]:
        raise ValueError("Whirlpool vault token mint mismatch")
    if a["amount_base_units"] == 0 or b["amount_base_units"] == 0:
        raise ValueError("Whirlpool has empty token vault")
    if a["authority"] != b["authority"]:
        raise ValueError("Whirlpool token vault authorities differ")
    return {"vault_a": a, "vault_b": b}
