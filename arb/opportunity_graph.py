"""Read-only arbitrage route discovery over VERIFIED on-chain liquidity pools.

Discover all 2-4 hop directed cycles (including distinct-pool same-venue and cross-venue)
without assuming that a pool decoder implies a usable quote or swap encoder.
No DEX HTTP APIs, fixed paths, mainnet submissions, or invented profit.
"""
import argparse,json,os
from collections import defaultdict
from arb.rpc import call
from arb.pool_registry import refresh
from arb.onchain_pool_discovery import discover,MINTS,VENUES
from arb.execution_target_matrix import TARGET_VENUES

MAX_HOPS=4
MAX_POOLS=200
MAX_CYCLES=2000

def cycles(pools,anchors=None,max_hops=MAX_HOPS,max_cycles=MAX_CYCLES,truncate=False,min_hops=2,hint_only=False,required_first_pool=None,
           max_edge_visits=None,search_stats=None,venue_priority=None):
    if venue_priority is not None and (not isinstance(venue_priority,dict)
            or set(venue_priority)!=set(TARGET_VENUES)
            or any(type(v) is not int or not 0<=v<=100 for v in venue_priority.values())):
        raise ValueError("invalid venue traversal priorities")
    if max_edge_visits is not None and (type(max_edge_visits) is not int or not 1<=max_edge_visits<=2_000_000):
        raise ValueError("invalid graph edge visit budget")
    if search_stats is not None and not isinstance(search_stats,dict):
        raise ValueError("invalid graph search stats")
    if required_first_pool is not None and (not isinstance(required_first_pool,(tuple,list))
            or len(required_first_pool)!=2 or required_first_pool[0] not in TARGET_VENUES
            or not isinstance(required_first_pool[1],str) or not required_first_pool[1]):
        raise ValueError("invalid required first pool identity")
    if type(hint_only) is not bool:raise ValueError("invalid hint-only graph flag")
    if type(truncate) is not bool:raise ValueError("invalid truncation flag")
    if type(max_hops) is not int or not 2<=max_hops<=6:
        raise ValueError("max_hops must be 2..6")
    if type(min_hops) is not int or not 2<=min_hops<=max_hops:
        raise ValueError("invalid minimum cycle length")
    if type(max_cycles) is not int or not 1<=max_cycles<=10000:
        raise ValueError("invalid cycle limit")
    if len(pools)>MAX_POOLS:raise ValueError("pool budget exceeded")
    edges=defaultdict(list)
    seen=set()
    for p in pools:
        if (not hint_only and not p.get("verified")) or len(p.get("mints",[]))!=2:
            continue
        a,b=p["mints"]
        venue,address=p.get("venue"),p.get("address")
        if venue not in TARGET_VENUES or a==b or not address:continue
        key=(venue,address)
        if key in seen:continue
        seen.add(key)
        for src,dst in ((a,b),(b,a)):
            edges[src].append({"input":src,"output":dst,"venue":venue,"pool":address})
    for token in edges:
        if venue_priority is None:
            edges[token].sort(key=lambda e:(e["output"],e["venue"],e["pool"]))
        else:
            edges[token].sort(key=lambda e:(venue_priority[e["venue"]],e["output"],e["venue"],e["pool"]))
    anchors=set(anchors) if anchors is not None else set(edges)
    if not anchors:raise ValueError("empty anchors")
    found=[];identities=set()
    edge_visits=0;stop_reason=None
    class BoundedDiscoveryComplete(Exception):pass
    def visit(start,current,path,used,visited):
        nonlocal edge_visits,stop_reason
        for e in edges[current]:
            if max_edge_visits is not None and edge_visits>=max_edge_visits:
                stop_reason="EDGE_VISIT_LIMIT"
                if truncate:raise BoundedDiscoveryComplete()
                raise ValueError("graph edge visit budget exceeded")
            edge_visits+=1
            if not path and required_first_pool is not None and (e["venue"],e["pool"])!=tuple(required_first_pool):
                continue
            if (e["venue"],e["pool"]) in used:continue
            nxt=e["output"]
            new=path+[e]
            if nxt==start:
                if len(new)<min_hops:continue
                identity=tuple((x["venue"],x["pool"],x["input"]) for x in new)
                if identity in identities:continue
                identities.add(identity)
                found.append({
                    "start_mint":start,"hops":len(new),
                    "legs":new,"venues":sorted(set(x["venue"] for x in new)),
                    "same_venue":len(set(x["venue"] for x in new))==1,
                    "status":"HINT_ONLY_UNQUOTED" if hint_only else "UNQUOTED","net_profit_lamports":None,
                    "simulation_verified":False,"opportunity_confirmed":False})
                if len(found)>=max_cycles:
                    if truncate:
                        stop_reason="CYCLE_LIMIT"
                        raise BoundedDiscoveryComplete()
                    if len(found)>max_cycles:raise ValueError("cycle budget exceeded")
            elif nxt not in visited and len(new)<max_hops:
                visit(start,nxt,new,used|{(e["venue"],e["pool"])},visited|{nxt})
    try:
        for anchor in sorted(anchors & set(edges)):
            visit(anchor,anchor,[],set(),{anchor})
    except BoundedDiscoveryComplete:
        pass
    if search_stats is not None:
        search_stats.update(edge_visits=edge_visits,stop_reason=stop_reason,
                            complete=stop_reason is None,returned_cycles=len(found),
                            venue_priority_traversal=venue_priority is not None)
    return found

def scan(rpc,registry,extra_pairs=(),anchors=None,max_cycles=MAX_CYCLES):
    if len(registry)>MAX_POOLS:raise ValueError("registry budget exceeded")
    verified=refresh(rpc,registry)
    pools=list(verified["verified_pools"])
    errors=list(verified["rejected"])
    if extra_pairs:
        discovered=discover(rpc,extra_pairs)
        errors.extend(discovered["errors"])
        existing={(p["venue"],p["address"]) for p in pools}
        # Discovery.verify has already checked ownership and reserves.
        for p in discovered["pools"]:
            if (p["venue"],p["address"]) not in existing:
                pools.append({**p,"verified":True})
                existing.add((p["venue"],p["address"]))
    if len(pools)>MAX_POOLS:raise ValueError("discovery pool budget exceeded")
    paths=cycles(pools,anchors,max_cycles=max_cycles)
    return {"status":"PARTIAL" if errors else "COMPLETE",
            "verified_pools":len(pools),"cyclic_routes":len(paths),
            "same_venue_routes":sum(x["same_venue"] for x in paths),
            "cross_venue_routes":sum(not x["same_venue"] for x in paths),
            "routes":paths,"validation_errors":errors,
            "quoted_routes":0,"simulated_routes":0,
            "confirmed_profitable_opportunities":0,
            "note":"Route topology only. Live amount-aware DEX quotes and atomic simulations are mandatory before profitability claims."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--registry",default="arb/pool_registry.json")
    p.add_argument("--extra-pairs",default="WSOL/RAY,USDC/RAY")
    p.add_argument("--anchors",default="WSOL,USDC,RAY")
    p.add_argument("--output",default=os.environ.get("ARB_GRAPH_REPORT",""))
    p.add_argument("--max-cycles",type=int,default=2000)
    args=p.parse_args()
    from arb.orca_whirlpool import SOL,USDC
    mints={**MINTS,"RAY":"4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"}
    anchors=[mints[x] for x in args.anchors.split(",") if x in mints]
    pairs=[]
    if args.extra_pairs:
        for x in args.extra_pairs.split(","):
            a,b=x.split("/")
            if a not in mints or b not in mints or a==b:raise ValueError("unsupported pair")
            pairs.append((mints[a],mints[b]))
    if len(pairs)>6:raise ValueError("pair budget exceeded")
    entries=json.load(open(args.registry))["pools"]
    report=scan(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),entries,pairs,anchors,args.max_cycles)
    print(json.dumps(report,indent=2))
    if args.output:
        with open(args.output,"w") as f:json.dump(report,f,indent=2)
    return 0 if report["status"]=="COMPLETE" else 2

if __name__=="__main__":raise SystemExit(main())
