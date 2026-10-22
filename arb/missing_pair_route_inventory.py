"""Prioritize missing cross-venue execution evidence from verified graph cycles.

This is a read-only route inventory: never declares pair execution verified.
"""
import json
import os
from collections import Counter
from arb.venue_capabilities import SWAP_BUILDERS, ATOMIC_PAIR_EVIDENCE
from arb.orca_whirlpool import SOL,USDC

def find_unverified_pairs(report):
    cycles=report.get("cycles")
    if not isinstance(cycles,list):
        raise ValueError("on-chain verified graph cycles required")
    candidates={}
    scanned=Counter()
    for cycle in cycles:
        if cycle.get("all_pools_onchain_verified") is not True:
            continue
        legs=cycle.get("legs",[])
        tokens=cycle.get("tokens",[])
        if (not 2<=len(legs)<=3 or len(tokens)!=len(legs)+1
                or tokens[0]!=tokens[-1] or tokens[0] not in (SOL,USDC)
                or any(l.get("from")!=tokens[i] or l.get("to")!=tokens[i+1]
                       for i,l in enumerate(legs))):
            continue
        venues=frozenset(l.get("venue") for l in legs)
        if len(venues)!=2 or not venues.issubset(SWAP_BUILDERS):
            continue
        if venues in ATOMIC_PAIR_EVIDENCE:
            continue
        pair=tuple(sorted(venues))
        scanned[pair]+=1
        item={"tokens":tokens,"legs":legs,"venue_pair":list(pair),
              "all_pools_onchain_verified":True,
              "atomic_signed_simulation_verified":False,
              "actionable":False,"broadcast":False}
        key=(len(legs),0 if tokens[0]==SOL else 1,
             tuple((l["venue"],l["pool"]) for l in legs))
        if pair not in candidates or key<candidates[pair][0]:
            candidates[pair]=(key,item)
    result=[{"pair":list(pair),"verified_candidate_routes":scanned[pair],
             "selected_route":candidates[pair][1],
             "atomic_signed_simulation_verified":False}
            for pair in sorted(candidates)]
    missing=[list(pair) for pair in sorted({
        tuple(sorted((a,b))) for a in SWAP_BUILDERS for b in SWAP_BUILDERS if a<b
    }-set( tuple(sorted(p)) for p in ATOMIC_PAIR_EVIDENCE))]
    return {"status":"MISSING_ATOMIC_PAIR_VERIFIED_ROUTE_INVENTORY",
            "missing_historical_pairings":missing,
            "pairings_with_verified_closed_route_candidates":len(result),
            "candidates":result,
            "no_candidate_does_not_imply_unsupported":True,
            "actionable":False,"live_execution_approved":False,"broadcast":False}

def main():
    with open(os.environ["TOKEN_GRAPH_VERIFICATION_REPORT"]) as stream:
        verified=json.load(stream)
    out=find_unverified_pairs(verified)
    with open(os.environ["TOKEN_MISSING_PAIR_ROUTE_REPORT"],"w") as stream:
        json.dump(out,stream,indent=2)
    print(json.dumps({"status":out["status"],
          "pairings_with_verified_closed_route_candidates":
          out["pairings_with_verified_closed_route_candidates"],
          "broadcast":False}))
if __name__=="__main__":
    main()
