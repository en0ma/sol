"""Single signed Orca SwapV2 attempt against authenticated local fork accounts.

Read-only fork: no surfnet_setAccount, no sendTransaction, no secrets or writes.
The newly generated fee payer and user token accounts do not exist on the fork;
a pre-execution failure is expected and must be reported as a blocker, never
as evidence of an executable swap.
"""
import base64
import json
import os
from solders.hash import Hash
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from arb.rpc import call
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc
from arb.orca_token2022_validation import snapshot
from arb.orca_token2022_quote_screen import directional_tick_array_candidates
from arb.orca_swap_v2_fixture_probe import CANDIDATE_POOL
from arb.orca_swap_v2_candidate import unsigned_swap_v2_candidate
from arb.orca_swap_v2_metas import ACCOUNT_ROLES, WRITABLE, SIGNERS, MEMO_PROGRAM

def prepare_authenticated_attempt(observed, signer, account_a, account_b, *, a_to_b=True):
    if not isinstance(observed, dict) or observed.get("structurally_verified") is not True:
        raise ValueError("authenticated Whirlpool snapshot required")
    if not isinstance(signer, Keypair) or type(a_to_b) is not bool:
        raise ValueError("ephemeral signer and exact direction required")
    pool = observed["pool"]
    mint_accounts = observed["mint_accounts"]
    if len(mint_accounts) != 2:
        raise ValueError("mint program evidence incomplete")
    ticks = directional_tick_array_candidates(pool, observed["tick_arrays"], a_to_b)
    if not ticks["all_present"]:
        raise ValueError("directional tick arrays incomplete")
    oracle = observed.get("oracle_evidence") or {}
    if not oracle.get("same_slot_verified") or not oracle.get("address"):
        raise ValueError("initialized same-slot oracle absent")
    addresses = {
        "token_program_a": mint_accounts[0]["owner"],
        "token_program_b": mint_accounts[1]["owner"],
        "memo_program": MEMO_PROGRAM,
        "token_authority": str(signer.pubkey()),
        "whirlpool": observed["address"],
        "token_mint_a": observed["mints"][0],
        "token_mint_b": observed["mints"][1],
        "token_owner_account_a": account_a,
        "token_vault_a": pool["token_vault_a"],
        "token_owner_account_b": account_b,
        "token_vault_b": pool["token_vault_b"],
        "oracle": oracle["address"],
    }
    for i, address in enumerate(ticks["addresses"]):
        addresses[f"tick_array_{i}"] = address
    for value in addresses.values():
        Pubkey.from_string(value)
    metas = [{"role": role, "address": addresses[role],
              "is_writable": i in WRITABLE, "is_signer": i in SIGNERS}
             for i, role in enumerate(ACCOUNT_ROLES)]
    candidate = unsigned_swap_v2_candidate(
        metas, 1, 0, 2**64, True, a_to_b)
    return candidate["instruction"]

def run(rpc, pool=CANDIDATE_POOL):
    require_loopback_rpc(rpc)
    # This is exclusively a read-only diagnostic for mainnet-backed local forks.
    report = {"status": "SIGNED_SWAPV2_ATTEMPT_BLOCKED",
              "pool": pool, "signed_simulation_verified": False,
              "actionable": False, "executable_quote": False, "broadcast": False}
    try:
        observed = snapshot(rpc, pool, include_ticks=True, include_oracle=True)
        signer = Keypair()
        users = [str(Keypair().pubkey()), str(Keypair().pubkey())]
        instruction = prepare_authenticated_attempt(observed, signer, *users)
        latest = call(rpc, "getLatestBlockhash", [{"commitment": "confirmed"}])
        tx = Transaction.new_signed_with_payer(
            [instruction], signer.pubkey(), [signer],
            Hash.from_string(latest["value"]["blockhash"]))
        simulation = call(rpc, "simulateTransaction", [
            base64.b64encode(bytes(tx)).decode(),
            {"encoding": "base64", "sigVerify": True,
             "replaceRecentBlockhash": False, "commitment": "confirmed"}])
        value = simulation.get("value") if isinstance(simulation, dict) else None
        if not isinstance(value, dict):
            raise ValueError("simulation response missing")
        report.update({
            "status": ("UNFUNDED_EPHEMERAL_ACCOUNTS_UNEXPECTED_SUCCESS"
                       if value.get("err") is None else "SIGNED_SWAPV2_ATTEMPT_REJECTED"),
            "pool_snapshot_slot": observed["slot"],
            "signature_verification_requested": True,
            "simulation_error": value.get("err"),
            "simulation_logs": value.get("logs"),
            "compute_units_consumed": value.get("unitsConsumed"),
            "ephemeral_user_accounts_provisioned": False,
            "ephemeral_fee_payer_provisioned": False,
        })
        # Simulation success without authenticated user state is not a verified swap.
        return report
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        report["blocker"] = type(exc).__name__ + ": " + str(exc)[:240]
        return report

if __name__ == "__main__":
    print(json.dumps(run(os.environ.get("SOLANA_RPC_URL", "http://127.0.0.1:8899"))))
