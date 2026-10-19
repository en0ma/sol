"""Read-only authenticated Whirlpool fixture screen on local Surfpool fork.

Produces candidate account provenance, never authorizes swaps.
"""
import json
import os
from arb.orca_token2022_validation import snapshot
from arb.orca_token2022_quote_screen import directional_tick_array_candidates
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc

CANDIDATE_POOL = "94BpFoyri4uTT55NFSHKYNFyUMtoWXEisMA4LK7nTKPU"

def classify(observed):
    if not isinstance(observed, dict) or observed.get("structurally_verified") is not True:
        raise ValueError("unverified Whirlpool snapshot")
    state = observed["pool"]
    arrays = observed.get("tick_arrays") or []
    directions = {}
    for name, direction in (("a_to_b", True), ("b_to_a", False)):
        candidate = directional_tick_array_candidates(state, arrays, direction)
        directions[name] = {
            "tick_array_addresses": candidate["addresses"],
            "tick_array_starts": candidate["starts"],
            "tick_arrays_complete": candidate["all_present"],
        }
    risk = observed.get("extension_risk") or {}
    oracle = observed.get("oracle_evidence") or {}
    blockers = []
    if not any(d["tick_arrays_complete"] for d in directions.values()):
        blockers.append("DIRECTIONAL_TICKS_INCOMPLETE")
    if risk.get("requires_specialized_quote_support", True):
        blockers.append("MINT_EXTENSIONS_REQUIRE_REVIEW")
    if not oracle.get("same_slot_verified", False):
        blockers.append("ORACLE_NOT_INITIALIZED_IN_SNAPSHOT")
    return {
        "status": "STRUCTURAL_FIXTURE_OBSERVED",
        "pool_address": observed["address"],
        "snapshot_slot": observed["slot"],
        "mints": observed["mints"],
        "mint_token_programs": [m["owner"] for m in observed["mint_accounts"]],
        "vaults": [state["token_vault_a"], state["token_vault_b"]],
        "directions": directions,
        "oracle": {"address": oracle.get("address"), "same_slot_verified": oracle.get("same_slot_verified", False)},
        "extension_risk": risk,
        "blockers": blockers,
        "account_fixture_execution_verified": False,
        "signed_simulation_verified": False,
        "actionable": False,
        "executable_quote": False,
        "broadcast": False,
    }

def run(rpc, pool=CANDIDATE_POOL):
    require_loopback_rpc(rpc)
    try:
        return classify(snapshot(rpc, pool, include_ticks=True, include_oracle=True))
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        return {
            "status": "FIXTURE_NOT_VERIFIED", "pool_address": pool,
            "blockers": [type(exc).__name__ + ": " + str(exc)[:240]],
            "signed_simulation_verified": False,
            "actionable": False, "executable_quote": False, "broadcast": False,
        }

if __name__ == "__main__":
    print(json.dumps(run(os.environ.get("SOLANA_RPC_URL", "http://127.0.0.1:8899"))))
