"""M5: screen observed authenticated route quotes, without live trade claims."""
from arb.opportunity_research import evaluate_cycle, SAFETY

def screen(route, quotes, costs, *, now, max_age=60):
    edges=route.get("legs")
    if not isinstance(edges,list) or not 2<=len(edges)<=6 or not isinstance(quotes,list) or len(edges)!=len(quotes):
        raise ValueError("each cycle leg requires an observed quote")
    required=("venue","pool","input_mint","output_mint")
    for i,(edge,q) in enumerate(zip(edges,quotes)):
        if not isinstance(edge,dict) or not isinstance(q,dict) or any(
            not isinstance(edge.get(k),str) or not edge[k] or edge[k]!=q.get(k) for k in required
        ):
            raise ValueError(f"quote {i} route identity mismatch")
    report=evaluate_cycle({"start_mint":route.get("start_mint"),"legs":quotes,
                           "costs_start_mint_units":costs},
                          as_of_unix=now,max_age_seconds=max_age)
    return {**report,"quote_model_only":True,"requires_signed_simulation":True,
            "opportunity_confirmed":False}

def shortlist(routes,quotes_by_index,costs_by_index,*,now,limit=100):
    if not isinstance(routes,list) or len(routes)>2000 or type(limit)is not int or not 1<=limit<=2000:
        raise ValueError("invalid bounded research inventory")
    results=[]
    for i,route in enumerate(routes):
        if i not in quotes_by_index or i not in costs_by_index:
            results.append({"route_index":i,"status":"UNASSESSABLE",
                "reason_codes":["quotes or converted costs missing"],
                "conservative_net_start_mint_units":None,"opportunity_confirmed":False,**SAFETY})
            continue
        results.append({"route_index":i,**screen(route,quotes_by_index[i],costs_by_index[i],now=now)})
    ranked=sorted((x for x in results if x["status"]=="RESEARCH_CANDIDATE_ONLY"),
        key=lambda x:x["conservative_net_start_mint_units"],reverse=True)
    return {"status":"M5_RESEARCH_ONLY","assessable_routes":len(ranked),
        "positive_declared_cost_candidates":sum(x["positive_after_declared_costs"] for x in ranked),
        "top_candidates":ranked[:limit],"all_route_results":results,
        "simulation_verified":False,"profitability_confirmed":False,**SAFETY}
