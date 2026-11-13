"""Deterministic pool-level closed-route discovery, 2–6 legs.

Only authenticated, fresh registry edges participate. Enumerates directed
pool choices, including repeated venue identities, without claiming executable
quotes or signed swap success. Never sends transactions.
"""
from collections import defaultdict

MAX_LEGS=6

def _index_edges(pools, *, min_slot=0):
    if type(min_slot) is not int or min_slot<0:
        raise ValueError("invalid minimum observation slot")
    out=defaultdict(list)
    identities=set()
    for item in pools:
        if not isinstance(item,dict):
            raise ValueError("invalid pool record")
        if item.get("authenticated") is not True or item.get("active",True) is not True:
            continue
        venue,pool=item.get("venue"),item.get("pool",item.get("address"))
        mints=item.get("mints")
        slot=item.get("slot")
        if (not isinstance(venue,str) or not venue or not isinstance(pool,str) or not pool
                or not isinstance(mints,(list,tuple)) or len(mints)!=2
                or any(not isinstance(x,str) or not x for x in mints)
                or mints[0]==mints[1] or type(slot) is not int or slot<min_slot):
            continue
        identity=(venue,pool)
        if identity in identities:
            raise ValueError("ambiguous duplicated authenticated pool identity")
        identities.add(identity)
        for a,b in ((mints[0],mints[1]),(mints[1],mints[0])):
            out[a].append({"venue":venue,"pool":pool,
                           "input_mint":a,"output_mint":b,"slot":slot})
    for edges in out.values():
        edges.sort(key=lambda x:(x["output_mint"],x["venue"],x["pool"]))
    return out

def enumerate_cycles(pools, *, start_mints=None, min_legs=2, max_legs=6,
                     min_slot=0, max_results=10000):
    if (type(min_legs) is not int or type(max_legs) is not int
            or not 2<=min_legs<=max_legs<=MAX_LEGS):
        raise ValueError("route length must be between 2 and 6")
    if type(max_results) is not int or max_results<1:
        raise ValueError("positive candidate cap required")
    edges=_index_edges(pools,min_slot=min_slot)
    starts=sorted(edges) if start_mints is None else sorted(set(start_mints))
    if any(not isinstance(m,str) or not m for m in starts):
        raise ValueError("invalid starting token")
    result=[]
    seen=set()
    def visit(origin,current,tokens,legs,used_pools):
        if len(legs)>=max_legs or len(result)>=max_results:
            return
        for edge in edges.get(current,[]):
            key=(edge["venue"],edge["pool"])
            if key in used_pools:
                continue
            target=edge["output_mint"]
            length=len(legs)+1
            if target==origin:
                if length<min_legs:
                    continue
                candidate=legs+[edge]
                # Same input token may appear as a different starting point;
                # preserve chosen start_mint but deduplicate exact pool path.
                signature=(origin,tuple((e["venue"],e["pool"],e["input_mint"],
                                          e["output_mint"]) for e in candidate))
                if signature not in seen:
                    seen.add(signature)
                    result.append({"start_mint":origin,"end_mint":origin,
                                   "tokens":tokens+[origin],
                                   "legs":candidate,"leg_count":length,
                                   "min_observation_slot":min(e["slot"] for e in candidate),
                                   "signed_atomic_simulation_verified":False,
                                   "actionable":False,"live_execution_approved":False,
                                   "broadcast":False})
                if len(result)>=max_results:
                    return
            elif length<max_legs and target not in tokens:
                visit(origin,target,tokens+[target],legs+[edge],used_pools|{key})
                if len(result)>=max_results:
                    return
    for origin in starts:
        visit(origin,origin,[origin],[],set())
        if len(result)>=max_results:
            break
    return result

def candidate_summary(pools, **kwargs):
    routes=enumerate_cycles(pools,**kwargs)
    by_length={n:0 for n in range(2,7)}
    for r in routes:
        by_length[r["leg_count"]]+=1
    return {"status":"AUTHENTICATED_POOL_GRAPH_CANDIDATES",
            "candidate_count":len(routes),"counts_by_leg":by_length,
            "routes":routes,"signed_atomic_simulation_verified":False,
            "actionable":False,"live_execution_approved":False,"broadcast":False}
