"""Audit why a source-authenticated venue graph lacks longer mint-simple cycles.

Read-only graph topology, no liquidity price or profitability assumptions.
"""
from collections import Counter,defaultdict
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def audit(readiness):
    from arb.next_ten_fork_pool_probe import PROGRAMS
    if readiness.get("source")!="READ_ONLY_MAINNET_BACKED_SURFPOOL" or any(readiness.get(k)is not False for k in SAFE):
        raise ValueError("unauthenticated source graph")
    groups=readiness.get("authenticated_pools")
    if not isinstance(groups,dict) or set(groups)!=set(PROGRAMS):
        raise ValueError("incomplete venue inventory")
    pairs=defaultdict(set);adj=defaultdict(set);rows=[]
    for venue,group in groups.items():
        if not isinstance(group,list):raise ValueError("invalid source venue group")
        for p in group:
            m=p.get("mints")
            if (p.get("venue")!=venue or p.get("authenticated")is not True
                    or any(p.get(k)is not False for k in SAFE)
                    or not isinstance(m,list) or len(m)!=2
                    or any(not isinstance(x,str) or not x for x in m)
                    or m[0]==m[1]):
                raise ValueError("source pool identity invalid")
            a,b=m;adj[a].add(b);adj[b].add(a)
            pairs[frozenset(m)].add(venue)
            rows.append((venue,a,b))
    degrees={mint:len(peers) for mint,peers in adj.items()}
    pair_sizes=Counter(len(v) for v in pairs.values())
    # The 2-core is a necessary (not sufficient) condition for a cycle of
    # length >=3; the induced token graph excludes parallel pool edges.
    remaining={k:set(v) for k,v in adj.items()}
    while True:
        leaves=[v for v,n in remaining.items() if len(n)<2]
        if not leaves:break
        for v in leaves:
            for other in remaining[v]:remaining[other].discard(v)
            del remaining[v]
    return {"status":"AUTHENTICATED_GRAPH_TOPOLOGY_DIAGNOSTIC",
        "authenticated_pools":len(rows),"distinct_token_mints":len(adj),
        "distinct_mint_pairs":len(pairs),
        "mint_pair_venue_multiplicity":{str(k):v for k,v in sorted(pair_sizes.items())},
        "degree_ge_two_mints":sum(d>=2 for d in degrees.values()),
        "two_core_mints":len(remaining),
        "two_core_mint_edges":sum(map(len,remaining.values()))//2,
        "degree_histogram":{str(k):v for k,v in sorted(Counter(degrees.values()).items())},
        "note":"Mint-simple longer cycles require sufficient token graph connectivity; source quotes still required.",
        **SAFE}
