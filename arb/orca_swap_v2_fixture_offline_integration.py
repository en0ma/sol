"""Exercise historical Orca mint identities on explicitly offline Surfpool.

Historical identities are test inputs, NOT current fork authentication. No swap
instruction or broadcast is assembled here.
"""
import json
import os
from solders.keypair import Keypair
from arb.orca_swap_v2_fixture_offline_provision import provision_offline_fixture_accounts
from arb.orca_swap_v2_fixture_user_readback import observe_fixture_user_accounts
from arb.orca_swap_v2_fixture_input_funding import check_fixture_input_funding
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc

HISTORICAL_MINT_A = "9ckR7pPPvyPadACDTzLwK2ZAEeUJ3qGSnzPs8bVaHrSy"
HISTORICAL_MINT_B = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
TOKEN_CLASSIC = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

def run(rpc):
    require_loopback_rpc(rpc)
    if os.environ.get("SURFPOOL_EXPLICITLY_OFFLINE") != "1":
        raise ValueError("explicit offline opt-in required")
    from arb.rpc import call
    slot_result = call(rpc, "getSlot", [{"commitment": "confirmed"}])
    if type(slot_result) is not int or slot_result < 0:
        raise ValueError("invalid offline context slot")
    plan = {
        "status": "USER_ACCOUNT_BINDING_PLAN_ONLY",
        "pool_snapshot_slot": slot_result,
        "required_accounts": [
            {"role": "token_owner_account_a", "mint": HISTORICAL_MINT_A,
             "token_program": TOKEN_2022},
            {"role": "token_owner_account_b", "mint": HISTORICAL_MINT_B,
             "token_program": TOKEN_CLASSIC},
        ],
    }
    signer = Keypair()
    provision = provision_offline_fixture_accounts(
        rpc, plan, signer, amounts=(1000000, 0))
    observed = observe_fixture_user_accounts(
        rpc, plan, provision["addresses"], str(signer.pubkey()))
    if observed["observed_balances_base_units"] != [1000000, 0]:
        raise ValueError("offline token balances did not round trip")
    funding = check_fixture_input_funding(
        observed, a_to_b=True, required_amount=100000)
    if not funding["input_balance_sufficient_for_gross_amount"]:
        raise ValueError("offline synthetic input funding missing")
    return {
        "status": "OFFLINE_SYNTHETIC_FIXTURE_ACCOUNTS_READ_BACK",
        "historical_fixture_mints_only": True,
        "offline_user_account_snapshot_slot": observed["user_account_snapshot_slot"],
        "mint_program_roles_verified": True,
        "synthetic_input_funding_observed": True,
        "real_pool_same_fork_verified": False,
        "runtime_token_account_semantics_verified": False,
        "signed_simulation_verified": False,
        "actionable": False, "executable_quote": False, "broadcast": False,
    }

if __name__ == "__main__":
    print(json.dumps(run(os.environ.get("SOLANA_RPC_URL", "http://127.0.0.1:8899"))))
