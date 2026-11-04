"""Read-only Orca program availability probe on a local Surfpool RPC.

No account mutation, signing, sendTransaction, or mainnet broadcasting.
"""
import json
import os
from arb.rpc import call
from arb.orca_whirlpool import PROGRAM
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc

UPGRADEABLE_LOADER = "BPFLoaderUpgradeab1e11111111111111111111111"

def classify_program(info):
    if not isinstance(info, dict):
        return {"status": "ORCA_PROGRAM_MISSING", "ready_for_pool_fixture": False}
    executable = info.get("executable") is True
    owner = info.get("owner")
    ready = executable and owner == UPGRADEABLE_LOADER
    return {
        "status": "ORCA_PROGRAM_EXECUTABLE" if ready else "ORCA_PROGRAM_NOT_VERIFIED",
        "executable": executable,
        "owner_matches_upgradeable_loader": owner == UPGRADEABLE_LOADER,
        "ready_for_pool_fixture": ready,
    }

def run(rpc):
    require_loopback_rpc(rpc)
    response = call(rpc, "getAccountInfo", [
        PROGRAM, {"encoding": "base64", "commitment": "confirmed"}
    ])
    result = classify_program(response.get("value"))
    result.update({
        "program_id": PROGRAM,
        "snapshot_slot": response.get("context", {}).get("slot"),
        "signed_simulation_verified": False,
        "actionable": False,
        "executable_quote": False,
        "broadcast": False,
    })
    return result

if __name__ == "__main__":
    print(json.dumps(run(os.environ.get("SOLANA_RPC_URL", "http://127.0.0.1:8899"))))
