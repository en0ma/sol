"""Plan fixture-specific SwapV2 user-account roles from authenticated pool evidence.

Read-only planning only. No account allocation, minting, signing or RPC writes.
The existing WSOL/USDC offline provisioning is intentionally unchanged.
"""
from arb.orca_swap_v2_local_token_accounts import TOKEN_PROGRAMS

def plan_user_account_binding(observed):
    if not isinstance(observed, dict) or observed.get("structurally_verified") is not True:
        raise ValueError("authenticated pool snapshot required")
    state = observed.get("pool")
    mints = observed.get("mints")
    mint_accounts = observed.get("mint_accounts")
    if not isinstance(state, dict) or not isinstance(mints, list) or len(mints) != 2 or len(set(mints)) != 2:
        raise ValueError("invalid pool mint identities")
    if not isinstance(mint_accounts, list) or len(mint_accounts) != 2:
        raise ValueError("missing mint owner evidence")
    if [state.get("token_mint_a"), state.get("token_mint_b")] != mints:
        raise ValueError("pool and mint evidence disagree")
    programs = [m.get("owner") if isinstance(m, dict) else None for m in mint_accounts]
    if any(p not in TOKEN_PROGRAMS for p in programs):
        raise ValueError("unsupported or missing mint token program")
    slot = observed.get("slot")
    if type(slot) is not int or slot < 0:
        raise ValueError("missing synchronized snapshot slot")
    return {
        "status": "USER_ACCOUNT_BINDING_PLAN_ONLY",
        "pool_address": observed.get("address"),
        "pool_snapshot_slot": slot,
        "required_accounts": [
            {"role": "token_owner_account_a", "mint": mints[0], "token_program": programs[0]},
            {"role": "token_owner_account_b", "mint": mints[1], "token_program": programs[1]},
        ],
        "required_authority": "EPHEMERAL_SIGNER_TO_BE_VERIFIED",
        "user_token_accounts_verified": False,
        "signer_control_verified": False,
        "same_fork_user_binding_verified": False,
        "signed_simulation_verified": False,
        "actionable": False,
        "executable_quote": False,
        "broadcast": False,
    }
