"""Prioritize distinct-pool indicative cycles for future atomic simulation.

This is a candidate queue, never an executable/profitable signal. A same-pool
round trip is not a substitute for cross-pool opportunity discovery.
"""
def shortlist(rankings,limit=20):
    if not isinstance(rankings,list) or type(limit)is not int or not 1<=limit<=100:
        raise ValueError("invalid indicative candidate queue")
    out=[]
    for route in rankings:
        if not isinstance(route,dict) or route.get("status")!="INDICATIVE_ONLY":
            continue
        legs=route.get("route_legs")
        if not isinstance(legs,list) or not 2<=len(legs)<=4:
            continue
        pools=[x.get("pool") for x in legs if isinstance(x,dict)]
        if len(pools)!=len(legs) or any(not isinstance(p,str) or not p for p in pools):
            continue
        if len(set(pools))<2:
            continue
        gross=route.get("estimated_gross_base_units")
        amount=route.get("input_base_units")
        if type(gross)is not int or type(amount)is not int or amount<=0:
            continue
        out.append({"start_mint":route["start_mint"],
                    "input_base_units":amount,"gross_base_units":gross,
                    "hops":len(legs),"unique_pools":len(set(pools)),
                    "unique_venues":len(set(x["venue"] for x in legs)),
                    "route_legs":[dict(x) for x in legs],
                    "priority":"POSITIVE_INDICATIVE_GROSS" if gross>0
                               else "NONPOSITIVE_INDICATIVE_GROSS",
                    "atomic_simulation_verified":False,
                    "actionable":False,"confirmed_profitable":False})
    # Partition by token denomination; never compare raw base-unit gross
    # amounts across different starting mints.
    out.sort(key=lambda x:(x["priority"]!="POSITIVE_INDICATIVE_GROSS",
                           x["start_mint"],-x["gross_base_units"],
                           -x["unique_venues"],x["input_base_units"]))
    return out[:limit]
