"""Read-only fixture user-account discovery gate for Surfpool fork CI.

Account addresses and public authority may be passed in environment variables;
no private keys, account writes, signing or broadcasting are performed.
"""
import json
import os
from arb.orca_swap_v2_fixture_probe import CANDIDATE_POOL
from arb.orca_token2022_validation import snapshot
from arb.orca_swap_v2_fixture_user_plan import plan_user_account_binding
from arb.orca_swap_v2_atomic_pool_user_readback import observe_atomic_pool_user_identities
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc
from arb.orca_swap_v2_fixture_input_funding import check_fixture_input_funding

def run(rpc, *, account_a=None, account_b=None, authority=None, a_to_b=None, required_amount=None):
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
        evidence = observe_atomic_pool_user_identities(rpc, plan, [account_a, account_b], authority)
    except (ValueError, TypeError, KeyError) as exc:
        result["status"] = "FIXTURE_USER_ACCOUNTS_NOT_VERIFIED"
        result["blockers"] = [type(exc).__name__ + ": " + str(exc)[:200]]
        return result
    evidence["user_token_accounts_verified"] = True
    evidence["same_atomic_pool_user_snapshot_verified"] = True
    if a_to_b is None and required_amount is None:
        evidence["funding_check_status"] = "INPUT_AMOUNT_NOT_CONFIGURED"
        return evidence
    if type(a_to_b) is not bool or type(required_amount) is not int:
        raise ValueError("direction and gross input amount must both be configured")
    funding_input = {
        "status": "FIXTURE_USER_ACCOUNTS_READBACK_VERIFIED",
        "observed_balances_base_units": evidence["observed_balances_base_units"],
        "balance_snapshot_slot": evidence["observation_slot"],
        "user_account_snapshot_slot": evidence["observation_slot"],
    }
    funding = check_fixture_input_funding(
        funding_input, a_to_b=a_to_b, required_amount=required_amount)
    evidence["funding_check"] = funding
    evidence["funding_check_status"] = funding["status"]
    return evidence

if __name__ == "__main__":
    print(json.dumps(run(
        os.environ.get("SOLANA_RPC_URL", "http://127.0.0.1:8899"),
        account_a=os.environ.get("ORCA_FIXTURE_USER_ACCOUNT_A"),
        account_b=os.environ.get("ORCA_FIXTURE_USER_ACCOUNT_B"),
        authority=os.environ.get("ORCA_FIXTURE_TOKEN_AUTHORITY"),
        a_to_b={"a_to_b": True, "b_to_a": False}.get(
            os.environ.get("ORCA_FIXTURE_INPUT_DIRECTION")),
        required_amount=(int(os.environ["ORCA_FIXTURE_GROSS_INPUT"])
                         if "ORCA_FIXTURE_GROSS_INPUT" in os.environ else None),
    )))
