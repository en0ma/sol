"""Offline empirical quote parity portfolio report with bounded risk screening.

Pairs source-bound two-leg quotes and signed receipts; empirical deviations
are diagnostic until independently attested. Costs must be explicit and in
start-mint base units; never approve broadcasts or claim profitability.
"""
from arb.signed_quote_accuracy_report import compare
from arb.opportunity_research import evaluate_cycle
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
COST_KEYS=frozenset({"network_fee","priority_fee","compute_cost","slippage_buffer","quote_uncertainty_buffer"})
def evaluate_cases(cases,*,as_of_unix,tolerance_bps=100,max_cases=100):
    if not isinstance(cases,list) or not 1<=len(cases)<=max_cases or type(max_cases)is not int or not 1<=max_cases<=1000:
        raise ValueError("bounded nonempty accuracy cases required")
    if type(as_of_unix)is not int or as_of_unix<0 or type(tolerance_bps)is not int or not 0<=tolerance_bps<=10000:
        raise ValueError("invalid timestamp or deviation tolerance")
    rows=[];seen=set()
    for case in cases:
        if not isinstance(case,dict) or set(("fixture","route","quotes","receipt"))-set(case):
            raise ValueError("complete signed quote research case required")
        f=case["fixture"];receipt=case["receipt"];quotes=case["quotes"];route=case["route"]
        pair=(f.get("first_venue"),f.get("second_venue"),f.get("first_pool"),f.get("second_pool"),f.get("state_account_manifest_sha256"))
        if pair in seen:raise ValueError("duplicate route and captured snapshot")
        seen.add(pair)
        accuracy=compare(f,route,quotes,receipt,tolerance_bps=tolerance_bps)
        costs=case.get("costs_start_mint_units")
        if not isinstance(costs,dict) or set(costs)!=COST_KEYS or any(type(x)is not int or x<0 for x in costs.values()):
            cost_status="UNASSESSABLE_MISSING_COSTS"
            research=None
        else:
            legs=[dict(q,quote_source=q.get("quote_source","ACCOUNT_DERIVED_INDICATIVE")) for q in quotes]
            research=evaluate_cycle({"start_mint":route.get("start_mint"),"legs":legs,
                                      "costs_start_mint_units":costs},as_of_unix=as_of_unix)
            cost_status=research["status"]
        rows.append({"venues":list(pair[:2]),"source_manifest":pair[4],
            "first_leg_deviation_bps":accuracy["first_leg_deviation_bps"],
            "second_leg_deviation_bps":accuracy["second_leg_deviation_bps"],
            "within_declared_tolerance_diagnostic":all(
              type(accuracy[k])is int and accuracy[k]<=tolerance_bps
              for k in ("first_leg_deviation_bps","second_leg_deviation_bps")),
            "signed_atomic_evidence_status":accuracy["signed_atomic_evidence_status"],
            "provenance_status":accuracy["provenance_status"],
            "cost_research_status":cost_status,
            "estimated_net_start_mint_units":research["conservative_net_start_mint_units"] if research else None,
            "measured_quote_accuracy_verified":False,"profitability_confirmed":False,**SAFE})
    return {"status":"OFFLINE_PARITY_RESEARCH_ONLY","sample_count":len(rows),
       "rows":rows,"validated_accuracy_samples":0,
       "live_execution_approved":False,"profitability_confirmed":False,**SAFE}
