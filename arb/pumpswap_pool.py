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
NATIVE_WSOL_MINT = "So11111111111111111111111111111111111111112"


def decode(raw):
    if not isinstance(raw, bytes) or len(raw) < BASE_LEN or raw[:8] != DISC:
        raise ValueError("unsupported PumpSwap Pool account")
    for start, end, label in ((245,261,"virtual quote reserves"),
                               (261,269,"creator fee bps"),
                               (269,270,"creator fee editing"),
                               (270,271,"holder reward flag"),
                               (271,279,"protocol fees"),
                               (279,287,"creator fees")):
        if start < len(raw) < end:
            raise ValueError("partial PumpSwap "+label+" extension")
    key = lambda offset: b58(raw[offset:offset+32])
    fields = {"creator": key(11), "base_mint": key(43),
              "quote_mint": key(75), "lp_mint": key(107),
              "base_vault": key(139), "quote_vault": key(171),
              "lp_supply": int.from_bytes(raw[203:211], "little"),
              "coin_creator": key(211),
              "is_mayhem_mode": raw[243],
              "is_cashback_coin": raw[244],
              "virtual_quote_reserves": (int.from_bytes(raw[245:261], "little", signed=True)
                                         if len(raw) >= 261 else 0),
              "creator_fee_bps": (int.from_bytes(raw[261:269], "little")
                                  if len(raw) >= 269 else 0),
              "can_edit_creator_fee": raw[269] if len(raw) >= 270 else 0,
              "is_holder_reward": raw[270] if len(raw) >= 271 else 0,
              "protocol_fees": (int.from_bytes(raw[271:279],"little") if len(raw)>=279 else None),
              "creator_fees": (int.from_bytes(raw[279:287],"little") if len(raw)>=287 else None)}
    if (len(set(fields[k] for k in ("base_mint", "quote_mint",
                                   "base_vault", "quote_vault"))) != 4
            or fields["is_mayhem_mode"] not in (0, 1)
            or fields["is_cashback_coin"] not in (0, 1)
            or fields["can_edit_creator_fee"] not in (0, 1)
            or fields["is_holder_reward"] not in (0, 1)
            or fields["creator_fee_bps"] > 10000):
        raise ValueError("invalid PumpSwap Pool fields")
    return fields


def verify(rpc, address, state, *, include_source_bytes=False):
    from arb.pumpswap_global_config import ADDRESS as CONFIG_ADDRESS, decode as decode_config
    from arb.pumpswap_fee_account import authenticated_address, decode_authenticated
    fee_address,_ = authenticated_address()
    keys = [address, state["base_vault"], state["quote_vault"], CONFIG_ADDRESS, fee_address, state["base_mint"]]
    resp = call(rpc, "getMultipleAccounts", [keys, {
        "encoding": "base64", "commitment": "confirmed"}])
    accounts = resp.get("value")
    slot = resp.get("context", {}).get("slot")
    if (type(slot) is not int or slot < 0 or not isinstance(accounts, list)
            or len(accounts) != 6):
        raise ValueError("incomplete PumpSwap account snapshot")
    pool = accounts[0]
    if (not pool or pool.get("owner") != PROGRAM or pool.get("executable")
            or decode(base64.b64decode(pool["data"][0], validate=True)) != state):
        raise ValueError("PumpSwap pool owner or state changed")
    config_account = accounts[3]
    if (not config_account or config_account.get("owner") != PROGRAM
            or config_account.get("executable")
            or config_account.get("data", [None,None])[1] != "base64"):
        raise ValueError("PumpSwap GlobalConfig missing from same-slot snapshot")
    config = decode_config(base64.b64decode(config_account["data"][0],validate=True))
    fee_config = decode_authenticated(accounts[4], address=fee_address)
    from arb.pumpswap_canonical import classify_pool
    canonical = classify_pool(state)
    from arb.token_vaults import TOKEN_PROGRAM
    mint_account = accounts[5]
    if (not mint_account or mint_account.get("owner") != TOKEN_PROGRAM
            or mint_account.get("executable") is not False
            or mint_account.get("data", [None,None])[1] != "base64"):
        raise ValueError("missing classic SPL base mint in snapshot")
    mint_data = base64.b64decode(mint_account["data"][0], validate=True)
    if len(mint_data) != 82 or mint_data[45] != 1:
        raise ValueError("unsupported or uninitialized PumpSwap base mint")
    base_supply = int.from_bytes(mint_data[36:44], "little")
    native_wsol_zero_supply = (state["base_mint"] == NATIVE_WSOL_MINT and base_supply == 0)
    if base_supply <= 0 and not native_wsol_zero_supply:
        raise ValueError("invalid PumpSwap base mint supply")
    balances = []
    for account, mint in zip(accounts[1:], (state["base_mint"], state["quote_mint"])):
        if not account or account.get("owner") != TOKEN_PROGRAM or account.get("executable"):
            raise ValueError("unsupported PumpSwap vault owner")
        token = decode_token_account(base64.b64decode(account["data"][0], validate=True))
        if token["mint"] != mint or token["authority"] != address:
            raise ValueError("PumpSwap vault mint or authority mismatch")
        balances.append(token["amount_base_units"])
    if (state["protocol_fees"] is not None and state["creator_fees"] is not None
            and state["protocol_fees"] + state["creator_fees"] > balances[1]):
        raise ValueError("PumpSwap accrued fees exceed quote vault")
    if min(balances) <= 0 or balances[1] + state["virtual_quote_reserves"] <= 0:
        raise ValueError("empty or invalid effective PumpSwap liquidity")
    from arb.pumpswap_fee_modes import compare_fee_modes
    if native_wsol_zero_supply:
        # The native mint's zero supply is not a usable market-cap input.
        # Preserve structural observations, but never invent a fee tier.
        fee_modes = {"status":"NATIVE_WSOL_SUPPLY_FEE_TIER_UNAVAILABLE",
                     "candidate_modes":{}, "unavailable_modes":{"standard":"zero native mint supply"},
                     "rates_equal":False, "fee_mode_verified":False,
                     "effective_fee_verified":False, "actionable":False}
    else:
        fee_modes = compare_fee_modes({
            "canonical_pool_verified":canonical["canonical_pool_verified"],
            "canonical":canonical["canonical"],"fee_config":fee_config,
            "base_mint_supply":base_supply,"base_reserve":balances[0],
            "quote_vault_balance":balances[1],
            "virtual_quote_reserves":state["virtual_quote_reserves"]})
    return {"venue": "pumpswap", "address": address, "verified": True,
            "base_mint": state["base_mint"], "quote_mint": state["quote_mint"],
            "base_vault":state["base_vault"],"quote_vault":state["quote_vault"],
            "coin_creator":state["coin_creator"],
            "is_mayhem_mode":state["is_mayhem_mode"],
            "is_cashback_coin":state["is_cashback_coin"],
            "base_reserve": balances[0], "quote_vault_balance": balances[1],
            "base_mint_supply": base_supply,
            "native_wsol_zero_supply": native_wsol_zero_supply,
            "virtual_quote_reserves": state["virtual_quote_reserves"],
            "slot": slot, "creator_fee_bps": state["creator_fee_bps"],
            "protocol_fees_accrued": state["protocol_fees"],
            "creator_fees_accrued": state["creator_fees"],
            "global_config": config, "fee_config": fee_config,
            "fee_tier_candidate": fee_modes["candidate_modes"].get("standard"),
            "fee_mode_diagnostic": fee_modes,
            "canonical": canonical["canonical"],
            "canonical_pool_verified": canonical["canonical_pool_verified"],
            "fee_mode_verified": False,
            "effective_fee_verified": False, "fee_verified_onchain": False,
            "actionable": False, "executable_quote": False,
            **({"authenticated_source_accounts": [
                {"address": key, "owner": item["owner"],
                 "account_base64": item["data"][0],
                 "lamports": item["lamports"], "executable": item["executable"]}
                for key, item in zip(keys, accounts)
            ]} if include_source_bytes else {})}
