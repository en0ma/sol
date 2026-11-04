"""Conservative instruction-builder readiness for verified closed-token cycles.

This is STATIC capability classification only, not executable routing, a
quote, or signed simulation. Unsupported assets/venues remain blocked.
"""
import json
import os
from collections import Counter
from arb.orca_whirlpool import SOL, USDC

SUPPORTED_ORCA = "orca"
SUPPORTED_CPMM = "raydium_cpmm"

def assess(graph):
    assessed = []
    for cycle in graph.get("cycles", []):
        legs = cycle.get("legs", [])
        tokens = cycle.get("tokens", [])
        if not legs or len(tokens) != len(legs) + 1 or tokens[0] != tokens[-1]:
            raise ValueError("invalid or non-closing route")
        if any((leg["from"], leg["to"]) != (tokens[i], tokens[i + 1])
               for i, leg in enumerate(legs)):
            raise ValueError("route legs do not follow token cycle")
        if not cycle.get("all_pools_onchain_verified"):
            stage, blockers = "POOL_VERIFICATION_BLOCKED", list(cycle.get("rejection_reasons") or [])
        else:
            blockers = []
            for leg in legs:
                if leg["venue"] == SUPPORTED_ORCA:
                    # Generic legacy Whirlpool instruction builder accepts both
                    # mint directions, but full route assembly remains missing.
                    continue
                if leg["venue"] == SUPPORTED_CPMM:
                    if (leg["from"], leg["to"]) not in ((SOL, USDC), (USDC, SOL)):
                        blockers.append("CPMM builder restricted to WSOL/USDC")
                else:
                    blockers.append("missing swap builder for " + leg["venue"])
            stage = "BUILDERS_PRESENT_ASSEMBLER_MISSING" if not blockers else "LEG_BUILDERS_MISSING"
        assessed.append({
            "tokens": tokens,
            "legs": legs,
            "stage": stage,
            "blockers": sorted(set(blockers)),
            "all_pools_onchain_verified": cycle.get("all_pools_onchain_verified") is True,
            "generic_atomic_route_assembler_ready": False,
            "quote_verified": False,
            "simulation_verified": False,
            "actionable": False,
            "live_execution_approved": False,
            "broadcast": False
        })
    return {
        "status": "EXECUTION_READINESS_CLASSIFICATION_ONLY",
        "cycles_assessed": len(assessed),
        "by_stage": dict(Counter(c["stage"] for c in assessed)),
        "cycles": assessed,
        "actionable": False, "broadcast": False, "live_execution_approved": False,
        "note": "Pool verification and instruction-builder presence do not establish account setup, valid tick arrays, profitable quotes, or atomic simulation."
    }

def main():
    with open(os.environ["TOKEN_GRAPH_VERIFICATION_REPORT"]) as stream:
        report = assess(json.load(stream))
    with open(os.environ["TOKEN_GRAPH_READINESS_REPORT"], "w") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps({k:v for k,v in report.items() if k != "cycles"},indent=2))

if __name__ == "__main__":
    main()
