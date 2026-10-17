"""Preserve ALL currently quoted cycle topologies for recurring rescans.

Profit is a per-snapshot prioritization, never a route blacklist. Distinct pools within a venue and cross-venue cycles remain discoverable even when their current gross is negative.
"""
def inventory(rankings):
    if not isinstance(rankings,list):
        raise ValueError("invalid cycle candidate inventory")
    result=[]
    for r in rankings:
        if not isinstance(r,dict):
            continue
        legs=r.get("route_legs")
        if not isinstance(legs,list) or not 2<=len(legs)<=4:
            continue
        if any(not isinstance(x,dict) or not isinstance(x.get("pool"),str)
               or not isinstance(x.get("venue"),str) for x in legs):
            continue
        pools={(x["venue"],x["pool"]) for x in legs}
        if len(pools)!=len(legs):
            continue
        venues={x["venue"] for x in legs}
        topology=("SAME_VENUE_MULTIPOOL" if len(venues)==1 else "CROSS_VENUE")
        gross=r.get("estimated_gross_base_units")
        status=r.get("status")
        if status!="INDICATIVE_ONLY" or type(gross)is not int:
            priority="WAIT_FOR_QUOTE"
        elif gross>0:
            priority="SCREEN_FOR_EXECUTION"
        else:
            priority="RESCAN_ON_NEXT_SNAPSHOT"
        result.append({"start_mint":r.get("start_mint"),
                       "input_base_units":r.get("input_base_units"),
                       "hops":len(legs),"topology":topology,
                       "route_legs":[dict(x) for x in legs],
                       "quote_status":status,"gross_base_units":gross if
                       type(gross)is int else None,
                       "current_priority":priority,
                       "eligible_for_future_rescan":True,
                       "actionable":False,"simulation_verified":False})
    return result
