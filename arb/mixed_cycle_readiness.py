"""Read-only execution feasibility inventory for verified mixed-venue cycles.

No swap is quoted or simulated. Does not fabricate unsupported program adapters.
"""
import json
import os
from collections import Counter
from arb.orca_whirlpool import SOL, USDC

SUPPORTED_BUILDERS = frozenset(("orca", "raydium_cpmm"))
MAX_REPORT_ROUTES = 50

def assess_mixed_routes(verified):
    cycles=verified.get("cycles", [])
    if not isinstance(cycles,list):
        raise ValueError("verified cycles list required")
    counts=Counter()
    routes=[]
    missing_venue_counts=Counter()
    missing_venue_sets=Counter()
    supported_venue_sets=Counter()
    prioritized=[]
    for cycle in cycles:
        if not cycle.get("all_pools_onchain_verified"):
            continue
        legs=cycle.get("legs",[])
        tokens=cycle.get("tokens",[])
        if not 2 <= len(legs) <= 3 or len(tokens)!=len(legs)+1 or tokens[0]!=tokens[-1]:
            continue
        venues=frozenset(leg.get("venue") for leg in legs)
        if len(venues)<2:
            continue
        counts["verified_cross_venue"]+=1
        missing=venues-SUPPORTED_BUILDERS
        missing_venue_sets[tuple(sorted(missing))]+=1
        supported_venue_sets[tuple(sorted(venues & SUPPORTED_BUILDERS))]+=1
        for v in missing:
            missing_venue_counts[v]+=1
        executable=not missing
        if executable:
            counts["available_builder_types"]+=1
        else:
            counts["unsupported_builder_types"]+=1
        if missing:
            prioritized.append({"tokens":tokens,"legs":legs,
                                "missing_venues":sorted(missing),
                                "missing_venue_count":len(missing),
                                "actionable":False,"broadcast":False})
        if len(routes)<MAX_REPORT_ROUTES:
            routes.append({"tokens":tokens,"legs":legs,
                           "builder_types_available":executable,
                           "unsupported_venues":sorted(venues-SUPPORTED_BUILDERS),
                           "signed_atomic_simulation_verified":False,
                           "actionable":False,"broadcast":False})
    prioritized.sort(key=lambda item:(
        item["missing_venue_count"],
        0 if item["tokens"][0]==SOL else 1 if item["tokens"][0]==USDC else 2,
        len(item["legs"]),
        tuple(item["missing_venues"]),
        tuple((leg["venue"],leg["pool"]) for leg in item["legs"])))
    priority_target = next((item for item in prioritized\n        if item["missing_venues"] == ["meteora_dlmm"]\n        and item["tokens"][0] in (SOL,USDC)), None)\n    prioritized_total=len(prioritized)
    prioritized=prioritized[:MAX_REPORT_ROUTES]
    return {"status":"MIXED_ROUTE_BUILDER_READINESS_ONLY",
            "prioritized_candidate_total":prioritized_total,
            "first_dlmm_only_offline_target":priority_target,
            "prioritized_candidates_truncated":prioritized_total>MAX_REPORT_ROUTES,
            "missing_venue_counts":dict(sorted(missing_venue_counts.items())),
            "missing_venue_combinations":[{"venues":list(k),"count":v}
                for k,v in sorted(missing_venue_sets.items(),key=lambda x:(-x[1],x[0]))],
            "supported_venue_combinations":[{"venues":list(k),"count":v}
                for k,v in sorted(supported_venue_sets.items(),key=lambda x:(-x[1],x[0]))],
            "candidate_routes_by_fewest_missing_builders":prioritized,
            "verified_cross_venue_cycles":counts["verified_cross_venue"],
            "verified_cross_venue_with_builder_types":counts["available_builder_types"],
            "verified_cross_venue_missing_builder_types":counts["unsupported_builder_types"],
            "verified_orca_cpmm_cycles":sum(
                c.get("all_pools_onchain_verified") and
                {l.get("venue") for l in c.get("legs",[])}=={"orca","raydium_cpmm"}
                for c in cycles),
            "routes":routes,
            "report_routes_capped":counts["verified_cross_venue"]>MAX_REPORT_ROUTES,
            "actionable":False,"live_execution_approved":False,"broadcast":False}

def main():
    with open(os.environ["TOKEN_GRAPH_VERIFICATION_REPORT"]) as stream:
        verified=json.load(stream)
    report=assess_mixed_routes(verified)
    with open(os.environ["TOKEN_MIXED_READINESS_REPORT"],"w") as stream:
        json.dump(report,stream,indent=2)
    print(json.dumps({k:v for k,v in report.items() if k!="routes"},indent=2))

if __name__=="__main__":
    main()
