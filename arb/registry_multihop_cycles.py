"""Bounded directed closed-cycle search over verified on-chain pool registry.

Each pool is traversable in either direction. Cycles start and finish at WSOL
or USDC, never reuse an intermediate token or pool, and never imply profit or
live execution readiness. Pure algorithm: no RPC calls, transactions or writes.
"""
from collections import defaultdict
from arb.orca_whirlpool import SOL, USDC

MAX_HOPS=8
MAX_CYCLES=5000
MAX_EDGES=50000

def discover_cycles(pools, *, min_hops=2, max_hops=5,
                    starts=(SOL,USDC), max_cycles=MAX_CYCLES):
    if type(min_hops) is not int or type(max_hops) is not int or not 2<=min_hops<=max_hops<=MAX_HOPS:
        raise ValueError("bounded 2..8 hop limits required")
    if type(max_cycles) is not int or not 1<=max_cycles<=MAX_CYCLES:
        raise ValueError("bounded cycle count required")
    if not isinstance(pools,list) or len(pools)>MAX_EDGES:
        raise ValueError("bounded list of registry pools required")
    if not isinstance(starts,(tuple,list)) or not starts or any(s not in (SOL,USDC) for s in starts):
        raise ValueError("only WSOL/USDC start assets supported")
    adjacency=defaultdict(list)
    for pool in pools:
        if not isinstance(pool,dict) or pool.get("all_pools_onchain_verified") is not True:
            continue
        venue=pool.get("venue")
        address=pool.get("pool") or pool.get("address")
        mints=pool.get("mints")
        if mints is not None and (not isinstance(mints,(list,tuple)) or len(mints)!=2):
            continue
        a=(mints[0] if mints is not None else pool.get("token_a") or pool.get("mint_a"))
        b=(mints[1] if mints is not None else pool.get("token_b") or pool.get("mint_b"))
        if not all(isinstance(x,str) and x for x in (venue,address,a,b)) or a==b:
            continue
        for source,target in ((a,b),(b,a)):
            adjacency[source].append((target,venue,address))
    for edges in adjacency.values():
        edges.sort(key=lambda e:(e[0],e[1],e[2]))
    results=[]
    unique=set()
    stopped=False
    def visit(start,current,tokens,legs,used_pools,used_tokens):
        nonlocal stopped
        if stopped:return
        for dest,venue,pool in adjacency[current]:
            if pool in used_pools:
                continue
            depth=len(legs)+1
            if dest==start:
                if depth>=min_hops:
                    key=(start,tuple((x["venue"],x["pool"],x["from"],x["to"]) for x in legs),
                         (venue,pool,current,start))
                    if key in unique:continue
                    unique.add(key)
                    full_legs=legs+[{"venue":venue,"pool":pool,"from":current,"to":start}]
                    results.append({"tokens":tokens+[start],"legs":full_legs,
                        "hop_count":depth,"venues":sorted({l["venue"] for l in full_legs}),
                        "all_pools_onchain_verified":True,
                        "signed_atomic_simulation_verified":False,
                        "actionable":False,"live_execution_approved":False,"broadcast":False})
                    if len(results)>=max_cycles:
                        stopped=True
                        return
                continue
            if depth>=max_hops or dest in used_tokens:
                continue
            visit(start,dest,tokens+[dest],legs+[{"venue":venue,"pool":pool,
                 "from":current,"to":dest}],used_pools|{pool},used_tokens|{dest})
            if stopped:return
    for start in dict.fromkeys(starts):
        visit(start,start,[start],[],set(),{start})
        if stopped:break
    return {"status":"VERIFIED_REGISTRY_GRAPH_CYCLE_DISCOVERY",
            "cycles":results,"cycle_count":len(results),
            "min_hops":min_hops,"max_hops":max_hops,
            "truncated":stopped,
            "actionable":False,"live_execution_approved":False,"broadcast":False}
