"""Fail-closed exact-input signed experiment assessment for three research priorities.

Only evaluates existing independently generated fixture/quote/receipt triplets.
Never synthesizes snapshot proof, pool quotes, execution fees or results.
"""
from arb.signed_quote_accuracy_report import compare
from arb.offline_risk_sensitivity import sensitivity
from arb.fixture_tick_coverage import coverage
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
REQUIRED_COSTS={"network_fee","priority_fee","compute_cost","slippage_buffer","quote_uncertainty_buffer"}
def assess_experiment(fixture,route,quotes,receipt,*,costs,extra_uncertainty_bps=100,tolerance_bps=100):
    accuracy=compare(fixture,route,quotes,receipt,tolerance_bps=tolerance_bps)
    reasons=[]
    if accuracy["signed_atomic_evidence_status"]!="VERIFIED":
        reasons.append("independent signed atomic evidence unverified")
    if accuracy["provenance_status"]=="UNVERIFIED":
        reasons.append("source-to-execution provenance unverified")
    if not isinstance(costs,dict) or set(costs)!=REQUIRED_COSTS or any(type(v)is not int or v<0 for v in costs.values()):
        reasons.append("measured or declared cost breakdown missing")
    initial=receipt.get("initial_balances_base_units") if isinstance(receipt,dict) else None
    final=receipt.get("positive_post_balances_base_units") if isinstance(receipt,dict) else None
    risk=None
    if (not reasons and isinstance(initial,list) and isinstance(final,list)
        and len(initial)==len(final)==3
        and all(type(v)is int and v>=0 for v in initial+final)
        and initial[0]>final[0] and final[2]>initial[2]):
        risk=sensitivity(input_units=initial[0]-final[0],
           observed_output_units=final[2]-initial[2],
           declared_cost_units=sum(costs.values()),
           extra_uncertainty_bps=extra_uncertainty_bps)
    if risk is None:reasons.append("observed risk assessment gated")
    gaps=[]
    if isinstance(fixture,dict) and any(fixture.get(k) in ("orca","raydium_clmm") for k in ("first_venue","second_venue")):
        ticks=coverage(fixture)
        gaps=[{"venue":p["venue"],"pool":p["pool"],
               "current_array_captured":p["current_array_captured"],
               "missing_intermediate_array_starts":p["missing_intermediate_array_starts"]}
              for p in ticks["rows"]]
        if any(not p["current_array_captured"] or p["missing_intermediate_array_starts"] for p in gaps):
            reasons.append("incomplete captured tick array coverage")
    return {"status":"OFFLINE_RESEARCH_EVIDENCE_ONLY",
       "quote_accuracy_diagnostic":accuracy,"cost_risk_diagnostic":risk,
       "concentrated_liquidity_gaps":gaps,"reason_codes":reasons,
       "signed_swap_quote_accuracy_independently_validated":False,
       "real_profitability_confirmed":False,**SAFE}
