"""Strict PumpSwap Pool decoder and synchronized vault snapshot.

Pool field offsets follow pump-fun/pump-public-docs PUMP_SWAP_README and
IDL Pool struct. Appended fields are EOF-tolerant, but partial fields are not.
Only classic SPL Token pools are admitted. Read-only.
"""
import base64
import hashlib
from arb.rpc import call
from arb.orca_whirlpool import b58
from arb.token_vaults import TOKEN_PROGRAM, decode_token_account

PROGRAM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
DISC = hashlib.sha256(b"account:Pool").digest()[:8]
BASE_LEN = 245


def decode(raw):
    if not isinstance(raw, bytes) or len(raw) < BASE_LEN or raw[:8] != DISC:
        raise ValueError("unsupported PumpSwap Pool account")
    if 245 < len(raw) < 261:
        raise ValueError("partial virtual quote reserves extension")
    key = lambda offset: b58(raw[offset:offset+32])
    fields = {"creator": key(11), "base_mint": key(43),
              "quote_mint": key(75), "lp_mint": key(107),
              "base_vault": key(139), "quote_vault": key(171),
              "lp_supply": int.from_bytes(raw[203:211], "little"),
              "coin_creator": key(211),
              "is_mayhem_mode": raw[243],
              "is_cashback_coin": raw[244],
              "virtual_quote_reserves": (int.from_bytes(raw[245:261], "little", signed=True)
                                         if len(raw) >= 261 else 0)}
    if (len(set(fields[k] for k in ("base_mint", "quote_mint",
                                   "base_vault", "quote_vault"))) != 4
            or fields["is_mayhem_mode"] not in (0, 1)
            or fields["is_cashback_coin"] not in (0, 1)):
        raise ValueError("invalid PumpSwap Pool fields")
    return fields


def verify(rpc, address, state):
    keys = [address, state["base_vault"], state["quote_vault"]]
    resp = call(rpc, "getMultipleAccounts", [keys, {
        "encoding": "base64", "commitment": "confirmed"}])
    accounts = resp.get("value")
    slot = resp.get("context", {}).get("slot")
    if (type(slot) is not int or slot < 0 or not isinstance(accounts, list)
            or len(accounts) != 3):
        raise ValueError("incomplete PumpSwap account snapshot")
    pool = accounts[0]
    if (not pool or pool.get("owner") != PROGRAM or pool.get("executable")
            or decode(base64.b64decode(pool["data"][0], validate=True)) != state):
        raise ValueError("PumpSwap pool owner or state changed")
    balances = []
    for account, mint in zip(accounts[1:], (state["base_mint"], state["quote_mint"])):
        if not account or account.get("owner") != TOKEN_PROGRAM or account.get("executable"):
            raise ValueError("unsupported PumpSwap vault owner")
        token = decode_token_account(base64.b64decode(account["data"][0], validate=True))
        if token["mint"] != mint or token["authority"] != address:
            raise ValueError("PumpSwap vault mint or authority mismatch")
        balances.append(token["amount_base_units"])
    if min(balances) <= 0 or balances[1] + state["virtual_quote_reserves"] <= 0:
        raise ValueError("empty or invalid effective PumpSwap liquidity")
    return {"venue": "pumpswap", "address": address, "verified": True,
            "base_mint": state["base_mint"], "quote_mint": state["quote_mint"],
            "base_reserve": balances[0], "quote_vault_balance": balances[1],
            "virtual_quote_reserves": state["virtual_quote_reserves"],
            "slot": slot, "fee_verified_onchain": False,
            "actionable": False, "executable_quote": False}
