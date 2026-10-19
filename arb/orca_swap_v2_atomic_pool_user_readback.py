"""Read-only single-response Whirlpool and user-account identity binding.

This proves pool and both supplied token accounts were observed in one RPC
context. It does NOT prove the signer controls the authority or permit a swap.
"""
import base64
from solders.pubkey import Pubkey
from arb.rpc import call
from arb.orca_whirlpool import PROGRAM, decode
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc, TOKEN_PROGRAMS

def observe_atomic_pool_user_identities(rpc, plan, addresses, authority):
    require_loopback_rpc(rpc)
    if not isinstance(plan, dict) or plan.get("status") != "USER_ACCOUNT_BINDING_PLAN_ONLY":
        raise ValueError("authenticated fixture plan required")
    pool_address = plan.get("pool_address")
    required = plan.get("required_accounts")
    minimum = plan.get("pool_snapshot_slot")
    planned_vaults = plan.get("pool_vault_addresses")
    if (not isinstance(planned_vaults, list) or len(planned_vaults) != 2 or
            any(not isinstance(v, str) or not v for v in planned_vaults) or
            len(set(planned_vaults)) != 2 or
            not isinstance(required, list) or len(required) != 2 or
            type(minimum) is not int or minimum < 0 or
            not isinstance(addresses, (list, tuple)) or len(addresses) != 2):
        raise ValueError("invalid user binding plan or addresses")
    try:
        keys = [str(Pubkey.from_string(key)) for key in (pool_address, *addresses, authority)]
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid account public key") from exc
    if len(set(keys[:3])) != 3:
        raise ValueError("pool and user accounts must be distinct")
    response = call(rpc, "getMultipleAccounts", [keys[:3], {
        "encoding": "base64", "commitment": "confirmed", "minContextSlot": minimum}])
    slot = response.get("context", {}).get("slot") if isinstance(response, dict) else None
    values = response.get("value") if isinstance(response, dict) else None
    if type(slot) is not int or slot < minimum or not isinstance(values, list) or len(values) != 3:
        raise ValueError("missing synchronized pool and user snapshot")
    pool_info = values[0]
    if not isinstance(pool_info, dict) or pool_info.get("owner") != PROGRAM or pool_info.get("executable"):
        raise ValueError("pool owner missing or incorrect")
    pool_raw = _bytes(pool_info)
    pool = decode(pool_raw)
    if [pool.get("token_mint_a"), pool.get("token_mint_b")] != [r.get("mint") for r in required]:
        raise ValueError("pool token mints differ from authenticated plan")
    if [pool.get("token_vault_a"), pool.get("token_vault_b")] != planned_vaults:
        raise ValueError("pool vault identities changed since authenticated snapshot")
    balances = []
    for index, (info, needed) in enumerate(zip(values[1:], required)):
        if (not isinstance(needed, dict) or needed.get("role") != (
                "token_owner_account_a" if index == 0 else "token_owner_account_b")
                or needed.get("token_program") not in TOKEN_PROGRAMS or
                not isinstance(info, dict) or info.get("owner") != needed["token_program"]
                or info.get("executable")):
            raise ValueError("user token program or role mismatch")
        raw = _bytes(info)
        if (len(raw) < 165 or raw[108] != 1 or
                str(Pubkey.from_bytes(raw[:32])) != needed["mint"] or
                str(Pubkey.from_bytes(raw[32:64])) != keys[3]):
            raise ValueError("user mint, authority, or initialization mismatch")
        balances.append(int.from_bytes(raw[64:72], "little"))
    return {"status": "SAME_CONTEXT_POOL_USER_IDENTITIES_VERIFIED",
            "pool_address": keys[0], "observation_slot": slot,
            "user_token_accounts": keys[1:3],
            "observed_balances_base_units": balances,
            "same_context_pool_user_identities_verified": True,
            "signer_control_verified": False,
            "full_swap_account_set_verified": False,
            "signed_simulation_verified": False,
            "actionable": False, "executable_quote": False, "broadcast": False}

def _bytes(info):
    data = info.get("data")
    if not isinstance(data, list) or len(data) != 2 or data[1] != "base64":
        raise ValueError("unsupported account encoding")
    return base64.b64decode(data[0], validate=True)
