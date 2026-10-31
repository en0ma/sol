"""Real, mint-connected candidate discovery for the local Solana research registry.

The canonical pool registry is a set of hints, not authenticated liquidity.
Seed exact-mint searches from existing identities; each newly discovered pool
is independently owner, pool-layout and vault checked by onchain_pool_discovery.
No token-name-based route matching or fabricated pool identities.
"""
import argparse
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

from arb.onchain_pool_discovery import discover, VENUES
from arb.orca_whirlpool import SOL, USDC
from arb.pool_registry import refresh
from arb.registry_pair_reconciliation import reconcile

SAFE = {"actionable": False, "live_execution_approved": False, "broadcast": False}


def candidate_pairs(hints, *, max_pairs=30):
    if (not isinstance(hints, list) or len(hints)>200 or
            type(max_pairs) is not int or not 1<=max_pairs<=100):
        raise ValueError("bounded mint-pair source inventory required")
    pairs=defaultdict(set)
    mint_venues=defaultdict(set)
    frequency=Counter()
    for row in hints:
        if not isinstance(row,dict):
            raise ValueError("malformed registry hint")
        mint=row.get("mints")
        if mint is None:
            continue
        if (not isinstance(mint,list) or len(mint)!=2 or
                mint[0]==mint[1] or
                any(not isinstance(m,str) or len(m)<32 for m in mint)):
            raise ValueError("invalid registry mint identity")
        key=tuple(sorted(mint))
        venue=row.get("venue")
        if venue not in VENUES:
            continue
        pairs[key].add(venue)
        for m in key:
            mint_venues[m].add(venue)
            frequency[m]+=1
    # Prefer already shared pool pairs, then those touching highly
    # interconnected hub mints; pair discovery still requires actual RPC.
    ranked=sorted(pairs, key=lambda pair: (
        -len(pairs[pair]),
        -sum(len(mint_venues[m]) for m in pair),
        -sum(frequency[m] for m in pair),
        0 if SOL in pair else 1 if USDC in pair else 2,
        pair))
    return [list(x) for x in ranked[:max_pairs]]


def expand(rpc, hints, *, max_pairs=12, per_order_limit=8, target=20):
    if not isinstance(hints,list) or len(hints)>200:
        raise ValueError("bounded registry required")
    base=refresh(rpc,hints)
    # Search only trusted existing onchain identities for their exact pairs.
    # A bad/unverified hint must never inject arbitrary search seeds.
    seeds=candidate_pairs(base["verified_pools"],max_pairs=max_pairs)
    discovered=discover(rpc,seeds,limit=per_order_limit,
                        registry_entries=hints,venues=list(VENUES)) if seeds else {
                            "pools":[],"errors":[],"status":"NO_VERIFIED_SEEDS",
                            "venue_attempts":{}}
    joined={}
    for pool in base["verified_pools"]:
        joined[(pool["venue"],pool["address"])]=pool
    for pool in discovered["pools"]:
        key=(pool["venue"],pool["address"])
        if key not in joined:
            joined[key]={**pool,"verified":True}
    original={(p["venue"],p["address"]):dict(p) for p in hints
              if isinstance(p,dict) and p.get("venue") in VENUES and
              isinstance(p.get("address"),str)}
    for key in joined:
        if key not in original:
            original[key]={"venue":key[0],"address":key[1]}
    report=reconcile(list(original.values()),list(joined.values()),target=target)
    report["discovery_status"]=discovered["status"]
    report["discovery_searched_pairs"]=seeds
    report["discovery_errors"]=discovered["errors"]
    report["discovery_venue_attempts"]=discovered["venue_attempts"]
    report["registry_refresh_rejections"]=base["rejected"]
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--registry",default="arb/pool_registry.json")
    parser.add_argument("--rpc",default=os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"))
    parser.add_argument("--output",required=True)
    parser.add_argument("--clean-registry",required=True)
    parser.add_argument("--max-pairs",type=int,default=12)
    parser.add_argument("--min-per-venue",type=int,default=20)
    args=parser.parse_args()
    from arb.six_venue_pipeline import local_rpc_only
    local_rpc_only(args.rpc)
    registry=json.loads(Path(args.registry).read_text())["pools"]
    report=expand(args.rpc,registry,max_pairs=args.max_pairs,target=args.min_per_venue)
    Path(args.output).write_text(json.dumps(report,indent=2)+"\n")
    # Only verified accounts can enter this output; never overwrite the
    # original hints automatically, and never claim a target that wasn't met.
    clean={"note":"Source-authenticated mint-complete pool identities, revalidate each use",
           "pools":[{"venue":x["venue"],"address":x["address"],
                     "mints":x["mints"],"pair":x["pair"]}
                    for x in report["graph_pools"]]}
    Path(args.clean_registry).write_text(json.dumps(clean,indent=2)+"\n")
    print(json.dumps({"verified":report["admitted"],
                      "targets":report["venue_coverage"],
                      "seven_venue_target_met":report["seven_venue_target_met"]},indent=2))
    return 0 if report["seven_venue_target_met"] else 2


if __name__=="__main__":
    raise SystemExit(main())
