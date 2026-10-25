"""M5: fail-closed simulation-only research over closed, same-mint swap cycles.

Never promote a positive gross delta into an executable trade. All costs must
be expressed in the *same start-mint base units* to permit a net estimate.
Missing liquidity, freshness, quotes, or cost conversion stays UNASSESSABLE.
"""
from datetime import datetime, timezone

SAFETY={"actionable":False,"live_execution_approved":False,"broadcast":False}

def evaluate_cycle(candidate, *, as_of_unix, max_age_seconds=60):
    if type(as_of_unix) is not int or as_of_unix<0 or type(max_age_seconds) is not int or max_age_seconds<1:
        raise ValueError("invalid research freshness window")
    if not isinstance(candidate,dict):
        raise ValueError("candidate must be a dict")
    legs=candidate.get("legs")
    if not isinstance(legs,list) or not 2<=len(legs)<=4:
        raise ValueError("research requires 2 to 4 observed legs")
    reasons=[]
    mint=candidate.get("start_mint")
    first=legs[0]
    if not isinstance(mint,str) or not mint or first.get("input_mint")!=mint:
        reasons.append("start mint mismatch")
    amount=first.get("amount_in")
    if type(amount)is not int or amount<=0:
        reasons.append("initial amount invalid")
    previous=amount
    oldest=None
    for i,leg in enumerate(legs):
        if not isinstance(leg,dict):
            reasons.append(f"leg {i} malformed")
            continue
        for key in ("venue","pool","input_mint","output_mint","quote_source"):
            if not isinstance(leg.get(key),str) or not leg[key]:
                reasons.append(f"leg {i} lacks {key}")
        quoted=leg.get("amount_out")
        input_units=leg.get("amount_in")
        if type(quoted)is not int or quoted<=0 or type(input_units)is not int or input_units<=0:
            reasons.append(f"leg {i} quote amount missing")
        if i and leg.get("input_mint")!=legs[i-1].get("output_mint"):
            reasons.append(f"leg {i} mint discontinuity")
        if previous is not None and input_units!=previous:
            reasons.append(f"leg {i} amount discontinuity")
        previous=quoted if type(quoted)is int and quoted>0 else None
        observed=leg.get("observed_unix")
        if type(observed)is not int or observed<0 or observed>as_of_unix or as_of_unix-observed>max_age_seconds:
            reasons.append(f"leg {i} stale or future quote")
        elif oldest is None or observed<oldest:
            oldest=observed
        depth=leg.get("liquidity_input_units")
        if type(depth)is not int or depth<=0 or type(input_units)is not int or input_units>depth:
            reasons.append(f"leg {i} inadequate authenticated liquidity")
        if leg.get("source_authenticated") is not True:
            reasons.append(f"leg {i} source not authenticated")
    if legs[-1].get("output_mint")!=mint:
        reasons.append("route is not closed in start mint")
    cost_items=candidate.get("costs_start_mint_units")
    if not isinstance(cost_items,dict) or not cost_items:
        reasons.append("missing common-unit fee, compute and slippage costs")
        cost_items={}
    mandatory={"network_fee","priority_fee","compute_cost","slippage_buffer","quote_uncertainty_buffer"}
    if set(cost_items)!=mandatory or any(type(x)is not int or x<0 for x in cost_items.values()):
        reasons.append("cost breakdown incomplete or invalid")
    total_cost=sum(x for x in cost_items.values() if type(x)is int and x>=0)
    gross=(previous-amount if type(previous)is int and type(amount)is int and amount>0 else None)
    supported=not reasons
    net=gross-total_cost if supported else None
    return {"status":"RESEARCH_CANDIDATE_ONLY" if supported else "UNASSESSABLE",
            "start_mint":mint,"gross_start_mint_units":gross if supported else None,
            "estimated_costs_start_mint_units":total_cost if supported else None,
            "conservative_net_start_mint_units":net,
            "positive_after_declared_costs":net>0 if net is not None else False,
            "source_quote_age_seconds":as_of_unix-oldest if oldest is not None else None,
            "reason_codes":reasons,
            "observed_signed_atomic_execution":False,
            "profitability_confirmed":False,**SAFETY}
