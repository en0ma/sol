"""Read-only arbitrage route discovery over VERIFIED on-chain liquidity pools.

Discover all 2-4 hop directed cycles (including reused same-pool, same-venue and cross-venue)
without assuming that a pool decoder implies a usable quote or swap encoder.
No DEX HTTP APIs, fixed paths, mainnet submissions, or invented profit.
"""
import argparse,json,os
from collections import defaultdict
from arb.rpc import call
from arb.pool_registry import refresh
from arb.onchain_pool_discovery import discover,MINTS,VENUES

MAX_HOPS=4
MAX_POOLS=200
MAX_CYCLES=2000

def cycles(pools,anchors=None,max_hops=MAX_HOPS,max_cycles=MAX_CYCLES):
    if type(max_hops) is not int or not 2<=max_hops<=4:
        raise ValueError("max_hops must be 2..4")
    if type(max_cycles) is not int or not 1<=max_cycles<=10000:
        raise ValueError("invalid cycle limit")
    if len(pools)>MAX_POOLS:raise ValueError("pool budget exceeded")
    edges=defaultdict(list)
    seen=set()
    for p in pools:
        if not p.get("verified") or len(p.get("mints",[]))!=2:
            continue
        a,b=p["mints"]
        venue,address=p.get("venue"),p.get("address")
        if venue not in VENUES or a==b or not address:continue
        key=(venue,address)
        if key in seen:continue
        seen.add(key)
        for src,dst in ((a,b),(b,a)):
            edges[src].append({"input":src,"output":dst,"venue":venue,"pool":address})
    for token in edges:
        edges[token].sort(key=lambda e:(e["output"],e["venue"],e["pool"]))
    anchors=set(anchors) if anchors is not None else set(edges)
    if not anchors:raise ValueError("empty anchors")
    found=[];identities=set()
    def visit(start,current,path,used,visited):
        for e in edges[current]:
            nxt=e["output"]
            new=path+[e]
            if nxt==start:
                if len(new)<2:continue
                identity=tuple((x["venue"],x["pool"],x["input"]) for x in new)
                if identity in identities:continue
                identities.add(identity)
                found.append({
                    "start_mint":start,"hops":len(new),
                    "legs":new,"venues":sorted(set(x["venue"] for x in new)),
                    "same_venue":len(set(x["venue"] for x in new))==1,
                    "status":"UNQUOTED","net_profit_lamports":None,
                    "simulation_verified":False,"opportunity_confirmed":False})
                if len(found)>max_cycles:raise ValueError("cycle budget exceeded")
            elif nxt not in visited and len(new)<max_hops:
                visit(start,nxt,new,used,visited|{nxt})
    for anchor in sorted(anchors & set(edges)):
        visit(anchor,anchor,[],set(),{anchor})
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
