"""M5 deterministic research-only trade-size sweep across authenticated snapshots.

Every size is re-quoted through the actual supported venue math; net estimates
come exclusively from caller-provided common-start-token cost evidence.
No linear scaling of quotes, inferred fees, or live transactions.
"""
from arb.snapshot_research_runner import run_authenticated_snapshot
SAFETY={"actionable":False,"live_execution_approved":False,"broadcast":False}

def sweep(snapshot,*,as_of_unix,input_sizes,cost_provider,max_age=60):
    if not isinstance(input_sizes,list) or not 1<=len(input_sizes)<=16:
        raise ValueError("one to sixteen candidate sizes required")
    if any(type(x)is not int or not 0<x<2**64 for x in input_sizes):
        raise ValueError("invalid exact-input size")
    if len(set(input_sizes))!=len(input_sizes):
        raise ValueError("duplicate input size")
    if not callable(cost_provider):
        raise ValueError("authenticated cost conversion provider required")
    results=[]
    for size in sorted(input_sizes):
        report=run_authenticated_snapshot(
            snapshot,as_of_unix=as_of_unix,initial_input=size,
            cost_provider=cost_provider,max_age=max_age)
        results.append({"input_base_units":size,
            "assessable_routes":sum(x.get("status")=="RESEARCH_CANDIDATE_ONLY"
                                    for x in report["results"]),
            "research_positive":report["research_positive"],
            "routes":report["results"],
            "rejected_pools":report["snapshot_rejected_pools"]})
    candidates=[]
    for item in results:
        for route in item["routes"]:
            research=route.get("research",{})
            net=research.get("conservative_net_start_mint_units")
            if (research.get("status")=="RESEARCH_CANDIDATE_ONLY"
                    and research.get("positive_after_declared_costs") is True
                    and type(net)is int and net>0):
                candidates.append({"input_base_units":item["input_base_units"],
                    "route":route["route"],"net_estimate_base_units":net,
                    "requires_signed_simulation":True})
    candidates.sort(key=lambda x:x["net_estimate_base_units"],reverse=True)
    return {"status":"RESEARCH_TRADE_SIZE_SWEEP","sizes_tested":len(results),
            "size_reports":results,"ranked_candidates":candidates,
            "positive_declared_cost_estimates":len(candidates),
            "verified_profitable_opportunities":0,
            "signed_execution_proven_in_sweep":False,**SAFETY}
