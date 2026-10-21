"""Direction-specific Orca-only closed-cycle tick-array preflight.

Read-only. This does not assert that a swap quote, oracle, transaction
assembly or atomic simulation has succeeded.
"""
import json
import os
from arb.orca_whirlpool import fetch_pool
from arb.whirlpool_swap import inspect_swap_requirements
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc
from arb.rpc import RPCError

MAX_ROUTES = 15

def preflight(rpc, verified):
    require_loopback_rpc(rpc)
    result = {"status": "READ_ONLY_ORCA_CYCLE_PREFLIGHT",
              "routes": [], "actionable": False, "broadcast": False,
              "live_execution_approved": False}
    for cycle in verified.get("cycles", [])[:MAX_ROUTES]:
        if not cycle.get("all_pools_onchain_verified"):
            continue
        legs, tokens = cycle["legs"], cycle["tokens"]
        if tokens[0] != tokens[-1] or any(l["venue"] != "orca" for l in legs):
            continue
        checks = []
        for leg in legs:
            try:
                state = fetch_pool(rpc, leg["pool"])
                a, b = state["token_mint_a"], state["token_mint_b"]
                if (leg["from"], leg["to"]) == (a, b):
                    direction = "a_to_b"
                elif (leg["from"], leg["to"]) == (b, a):
                    direction = "b_to_a"
                else:
                    raise ValueError("on-chain mint order disagrees with leg")
                readiness = inspect_swap_requirements(rpc, leg["pool"])
                ready = readiness["directions"][direction]["available"] is True
                checks.append({"pool": leg["pool"], "direction": direction,
                               "tick_arrays_ready": ready,
                               "required_starts": readiness["directions"][direction]["required_starts"]})
            except (ValueError, KeyError, TypeError, RPCError, TimeoutError, OSError) as exc:
                checks.append({"pool": leg["pool"], "tick_arrays_ready": False,
                               "error": str(exc)[:240]})
        all_ready = len(checks) == len(legs) and all(c["tick_arrays_ready"] for c in checks)
        result["routes"].append({
            "tokens": tokens, "legs": legs, "checks": checks,
            "all_directional_tick_arrays_ready": all_ready,
            "status": "TICKS_READY_ASSEMBLY_REQUIRED" if all_ready else "TICKS_UNAVAILABLE",
            "signed_simulation_completed": False,
            "actionable": False, "live_execution_approved": False, "broadcast": False})
    result["routes_checked"] = len(result["routes"])
    result["routes_with_ready_ticks"] = sum(r["all_directional_tick_arrays_ready"] for r in result["routes"])
    return result

def main():
    with open(os.environ["TOKEN_GRAPH_VERIFICATION_REPORT"]) as f:
        verified = json.load(f)
    report = preflight(os.environ.get("SOLANA_RPC_URL", "http://127.0.0.1:8899"), verified)
    with open(os.environ["TOKEN_CYCLE_TICK_PREFLIGHT_REPORT"], "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != "routes"}, indent=2))

if __name__ == "__main__":
    main()
