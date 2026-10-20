"""Bounded, read-only discovery and signed simulation of alternate SOL/USDC venues.

All accounts originate from local fork RPC. No sendTransaction, airdrops or
remote writes in discovery; cross_venue.run uses only local ephemeral simulation.
A result is never live-actionable, including when simulated PnL is positive.
"""
import json
import os
from arb.orca_whirlpool import find_pair, SOL, USDC
from arb.raydium_cpmm import candidates, verify_vaults
from arb.cross_venue import run
from arb.cross_venue_sweep import evaluate
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc

MAX_ORCA = 4
MAX_RAYDIUM = 4
MAX_ROUTES = 6
TEST_USDC_BASE_UNITS = 10000

def discover_and_simulate(rpc, max_routes=MAX_ROUTES):
    require_loopback_rpc(rpc)
    if type(max_routes) is not int or not 1 <= max_routes <= MAX_ROUTES:
        raise ValueError("unbounded discovery disabled")
    result = {"status": "DISCOVERY_INCOMPLETE", "source": "LOCAL_MAINNET_BACKED_SURFPOOL",
              "broadcast": False, "live_execution_approved": False,
              "actionable": False, "routes": [], "rejections": []}
    # find_pair performs discriminator, owner and exact mint matching.
    orca = find_pair(rpc, SOL, USDC, max_results=20)
    orca = [p for p in orca if
            (p["token_mint_a"], p["token_mint_b"]) == (SOL, USDC)]
    result["orca_discovered"] = len(orca)
    # CPMM search is restricted to both orders of the exact same mints.
    raydium = candidates(rpc, max_candidates=20)
    eligible = []
    for address, state in sorted(raydium.items()):
        if (state["token_0_mint"], state["token_1_mint"]) != (SOL, USDC):
            continue
        try:
            evidence = verify_vaults(rpc, address, state)
            if evidence.get("verified") is True:
                eligible.append(address)
        except (ValueError, KeyError, TypeError) as e:
            result["rejections"].append({"raydium": address, "reason": str(e)})
    result["raydium_verified"] = len(eligible)
    result["orca_considered"] = min(len(orca), MAX_ORCA)
    result["raydium_considered"] = min(len(eligible), MAX_RAYDIUM)
    for pool in orca[:MAX_ORCA]:
        for ray in eligible[:MAX_RAYDIUM]:
            if len(result["routes"]) >= max_routes:
                break
            for reverse in (False, True):
                if len(result["routes"]) >= max_routes:
                    break
                route = {"orca": pool["address"], "raydium": ray,
                         "direction": "raydium_to_orca" if reverse else "orca_to_raydium",
                         "usdc_amount_base_units": TEST_USDC_BASE_UNITS,
                         "actionable": False, "broadcast": False}
                try:
                    simulated = run(rpc, pool["address"], ray, 1000000,
                                    TEST_USDC_BASE_UNITS, reverse=reverse)
                    route["simulation"] = {k: v for k, v in simulated.items()
                                           if k != "log_tail"}
                    route["decision"] = evaluate(simulated)
                except (ValueError, KeyError, TypeError) as e:
                    route["status"] = "SIMULATION_BLOCKED"
                    route["reason"] = str(e)
                result["routes"].append(route)
        if len(result["routes"]) >= max_routes:
            break
    result["status"] = "BOUNDED_DISCOVERY_COMPLETE"
    result["routes_tested"] = len(result["routes"])
    result["simulated_profitable_candidates"] = sum(
        r.get("decision", {}).get("simulated_profitable") is True
        for r in result["routes"])
    return result

def main():
    report = discover_and_simulate(
        os.environ.get("SOLANA_RPC_URL", "http://127.0.0.1:8899"))
    path = os.environ.get("CROSS_VENUE_DISCOVERY_REPORT")
    if path:
        with open(path, "w") as f:
            json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
