"""Offline-only synthetic user account provisioning from an authenticated role plan.

This local Surfpool cheatcode is not a chain transaction. A fixture captured
on a different fork is NOT same-fork validation. Never run against fork CI.
"""
import os
from solders.keypair import Keypair
from arb.rpc import call
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc, TOKEN_PROGRAMS
from arb.orca_swap_v2_offline_provision import token_account_bytes

def provision_offline_fixture_accounts(rpc, plan, signer, *, amounts=(1000000, 0)):
    require_loopback_rpc(rpc)
    if os.environ.get("SURFPOOL_EXPLICITLY_OFFLINE") != "1":
        raise ValueError("explicit offline Surfpool opt-in required")
    if not isinstance(plan, dict) or plan.get("status") != "USER_ACCOUNT_BINDING_PLAN_ONLY":
        raise ValueError("authenticated user-account plan required")
    required = plan.get("required_accounts")
    if not isinstance(required, list) or len(required) != 2:
        raise ValueError("two planned token accounts required")
    if not isinstance(signer, Keypair):
        raise ValueError("local ephemeral signing key required")
    if (not isinstance(amounts, (list, tuple)) or len(amounts) != 2 or
            any(type(x) is not int or not 0 <= x < 2**64 for x in amounts)):
        raise ValueError("invalid synthetic token amounts")
    authority = str(signer.pubkey())
    accounts = []
    for i, (expected, amount) in enumerate(zip(required, amounts)):
        if not isinstance(expected, dict) or expected.get("role") != (
                "token_owner_account_a" if i == 0 else "token_owner_account_b"):
            raise ValueError("incorrect planned token account roles")
        mint, program = expected.get("mint"), expected.get("token_program")
        if not isinstance(mint, str) or program not in TOKEN_PROGRAMS:
            raise ValueError("invalid planned token mint or program")
        address = str(Keypair().pubkey())
        raw = token_account_bytes(mint, authority, amount)
        call(rpc, "surfnet_setAccount", [address, {
            "lamports": 2039280, "data": raw.hex(),
            "owner": program, "executable": False
        }])
        accounts.append(address)
    return {"status": "OFFLINE_SYNTHETIC_USER_ACCOUNTS_PROVISIONED",
            "addresses": accounts, "authority": authority,
            "amounts_base_units": list(amounts),
            "runtime_token_account_semantics_verified": False,
            "same_fork_pool_user_snapshot_verified": False,
            "signed_simulation_verified": False,
            "actionable": False, "executable_quote": False, "broadcast": False}
