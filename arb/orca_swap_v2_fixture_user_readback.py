"""Read both fixture user token accounts atomically from a loopback fork RPC.

No provisioning, signer creation, transaction signing, or broadcast.
"""
import base64
from solders.pubkey import Pubkey
from arb.rpc import call
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc, TOKEN_PROGRAMS
from arb.orca_swap_v2_fixture_user_binding import verify_fixture_user_observations

def observe_fixture_user_accounts(rpc, plan, addresses, authority):
    require_loopback_rpc(rpc)
    if not isinstance(plan, dict) or plan.get("status") != "USER_ACCOUNT_BINDING_PLAN_ONLY":
        raise ValueError("verified fixture plan required")
    required = plan.get("required_accounts")
    if not isinstance(required, list) or len(required) != 2:
        raise ValueError("two required token account roles missing")
    if not isinstance(addresses, (list, tuple)) or len(addresses) != 2 or len(set(addresses)) != 2:
        raise ValueError("two distinct token accounts required")
    try:
        for key in (*addresses, authority):
            Pubkey.from_string(key)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid token account or authority public key") from exc
    minimum = plan.get("pool_snapshot_slot")
    if type(minimum) is not int or minimum < 0:
        raise ValueError("invalid pool snapshot slot")
    response = call(rpc, "getMultipleAccounts", [list(addresses), {
        "encoding": "base64", "commitment": "confirmed", "minContextSlot": minimum
    }])
    slot = response.get("context", {}).get("slot")
    values = response.get("value")
    if type(slot) is not int or slot < minimum or not isinstance(values, list) or len(values) != 2:
        raise ValueError("missing synchronized user account snapshot")
    observations = []
    for address, needed, account in zip(addresses, required, values):
        if not isinstance(needed, dict) or needed.get("token_program") not in TOKEN_PROGRAMS:
            raise ValueError("unsupported expected token program")
        if not isinstance(account, dict) or account.get("owner") != needed["token_program"] or account.get("executable") is True:
            raise ValueError("missing or incorrectly owned token account")
        data = account.get("data")
        if not isinstance(data, list) or len(data) != 2 or data[1] != "base64":
            raise ValueError("invalid token account encoding")
        raw = base64.b64decode(data[0], validate=True)
        if len(raw) < 165 or raw[108] != 1:
            raise ValueError("uninitialized or truncated token account")
        mint = str(Pubkey.from_bytes(raw[:32]))
        owner = str(Pubkey.from_bytes(raw[32:64]))
        if mint != needed.get("mint") or owner != authority:
            raise ValueError("token account mint or authority mismatch")
        amount = int.from_bytes(raw[64:72], "little")
        observations.append({
            "amount_base_units": amount,
            "account": address, "mint": mint, "authority": owner,
            "token_program": account["owner"], "slot": slot,
            "initialized": True, "local_rpc_verified": True
        })
    result = verify_fixture_user_observations(plan, *observations, authority)
    result["observed_balances_base_units"] = [item["amount_base_units"] for item in observations]
    result["balance_snapshot_slot"] = slot
    result["input_funding_verified"] = False
    result["observation_method"] = "getMultipleAccounts"
    result["same_context_user_accounts_verified"] = True
    return result
