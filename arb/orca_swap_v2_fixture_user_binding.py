"""Fail-closed binding of local token-account observations to a Whirlpool fixture plan.

Account data is evidence only; this never proves signer key custody or authorizes a swap.
"""
from arb.orca_swap_v2_local_token_accounts import TOKEN_PROGRAMS

def verify_fixture_user_observations(plan, account_a, account_b, authority):
    if not isinstance(plan, dict) or plan.get("status") != "USER_ACCOUNT_BINDING_PLAN_ONLY":
        raise ValueError("authenticated fixture account plan required")
    required = plan.get("required_accounts")
    if not isinstance(required, list) or len(required) != 2:
        raise ValueError("two fixture account roles required")
    if not isinstance(authority, str) or not authority:
        raise ValueError("missing token account authority")
    slot = plan.get("pool_snapshot_slot")
    if type(slot) is not int or slot < 0:
        raise ValueError("invalid pool snapshot slot")
    accounts = (account_a, account_b)
    observed_slots = []
    addresses = []
    for expected_role, needed, observed in zip(
        ("token_owner_account_a", "token_owner_account_b"), required, accounts
    ):
        if not isinstance(needed, dict) or needed.get("role") != expected_role:
            raise ValueError("fixture account role ordering mismatch")
        if not isinstance(observed, dict) or observed.get("local_rpc_verified") is not True:
            raise ValueError("local user account readback missing")
        if (needed.get("token_program") not in TOKEN_PROGRAMS or
            observed.get("token_program") != needed["token_program"] or
            observed.get("mint") != needed.get("mint") or
            observed.get("authority") != authority or
            observed.get("initialized") is not True):
            raise ValueError("fixture token mint/program/authority mismatch")
        if type(observed.get("slot")) is not int or observed["slot"] < slot:
            raise ValueError("user token observation predates pool evidence")
        if not isinstance(observed.get("account"), str) or not observed["account"]:
            raise ValueError("missing token account address")
        observed_slots.append(observed["slot"])
        addresses.append(observed["account"])
    if len(set(addresses)) != 2 or len(set(observed_slots)) != 1:
        raise ValueError("user token accounts not distinct or same-slot observed")
    return {
        "status": "FIXTURE_USER_ACCOUNTS_READBACK_VERIFIED",
        "user_account_snapshot_slot": observed_slots[0],
        "pool_snapshot_slot": slot,
        "same_atomic_pool_user_snapshot_verified": False,
        "signer_control_verified": False,
        "signed_simulation_verified": False,
        "actionable": False,
        "executable_quote": False,
        "broadcast": False,
    }
