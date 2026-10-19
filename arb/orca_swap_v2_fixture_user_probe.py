"""Read-only fixture user-account discovery gate for Surfpool fork CI.

Account addresses and public authority may be passed in environment variables;
no private keys, account writes, signing or broadcasting are performed.
"""
import json
import os
from arb.orca_swap_v2_fixture_probe import CANDIDATE_POOL
from arb.orca_token2022_validation import snapshot
from arb.orca_swap_v2_fixture_user_plan import plan_user_account_binding
from arb.orca_swap_v2_fixture_user_readback import observe_fixture_user_accounts
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc

def run(rpc, *, account_a=None, account_b=None, authority=None):
    require_loopback_rpc(rpc)
    result = {"status": "FIXTURE_USER_ACCOUNTS_NOT_CONFIGURED",
              "blockers": ["USER_ACCOUNT_ADDRESSES_OR_AUTHORITY_MISSING"],
              "user_token_accounts_verified": False,
              "signer_control_verified": False,
              "same_atomic_pool_user_snapshot_verified": False,
              "signed_simulation_verified": False,
              "actionable": False, "executable_quote": False, "broadcast": False}
    if not all((account_a, account_b, authority)):
        return result
    observed = snapshot(rpc, CANDIDATE_POOL, include_ticks=False, include_oracle=False)
    plan = plan_user_account_binding(observed)
    try:
        evidence = observe_fixture_user_accounts(rpc, plan, [account_a, account_b], authority)
    except (ValueError, TypeError, KeyError) as exc:
        result["status"] = "FIXTURE_USER_ACCOUNTS_NOT_VERIFIED"
        result["blockers"] = [type(exc).__name__ + ": " + str(exc)[:200]]
        return result
    return evidence

if __name__ == "__main__":
    print(json.dumps(run(
        os.environ.get("SOLANA_RPC_URL", "http://127.0.0.1:8899"),
        account_a=os.environ.get("ORCA_FIXTURE_USER_ACCOUNT_A"),
        account_b=os.environ.get("ORCA_FIXTURE_USER_ACCOUNT_B"),
        authority=os.environ.get("ORCA_FIXTURE_TOKEN_AUTHORITY"),
    )))
