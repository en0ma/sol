"""Evaluate a real authenticated 2–6-hop fixture using each venue quote adapter.

Propagate BOTH endpoints of source-derived output intervals. This reveals
downstream liquidity/fee uncertainty instead of terminating at the first
complex venue. A hypothetical DAMM model remains hypothetical through the
entire path; neither scenario endpoint constitutes protocol-exact pricing.
"""
from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.fixture_all_venue_signed_quotes import quote_leg
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}

def walk(fixture,*,input_base_units,observed_unix,max_branches=16):
    if (type(input_base_units)is not int or not 0<input_base_units<2**64 or
            type(observed_unix)is not int or observed_unix<0 or
            type(max_branches)is not int or not 2<=max_branches<=128 or
            any(fixture.get(k)is not False for k in SAFE)):
        raise ValueError("safe source multihop interval quote required")
    rows=extract_pool_states(fixture)
    mints=fixture.get("route_mints")
    if (not 2<=len(rows)<=6 or not isinstance(mints,list)
            or len(mints)!=len(rows)+1 or mints[0]!=mints[-1]):
        raise ValueError("closed source multihop route required")
    for i,row in enumerate(rows):
        if set(row["mints"])!={mints[i],mints[i+1]}:
            raise ValueError("source route mint discontinuity")
        if row["snapshot_slot"]!=fixture["state_accounts_observed_slot"]:
            raise ValueError("route source slot discontinuity")
    branches=[{"amount":input_base_units,"trace":[],
               "hypothetical":False,"source_bounded":False}]
    failures=[]
    for index,row in enumerate(rows):
        following=[]
        for branch in branches:
            q=quote_leg(fixture,leg_index=index,amount_in=branch["amount"],
                        observed_unix=observed_unix)
            if (not isinstance(q,dict) or any(q.get(k)is not False for k in SAFE)
                    or q.get("pool")!=row["address"]
                    or q.get("venue")!=row["venue"]
                    or q.get("source_slot")!=fixture["state_accounts_observed_slot"]):
                raise ValueError("source native quote binding missing")
            status=q.get("quote_status")
            if status=="SOURCE_BOUND_INDICATIVE":
                output=q.get("predicted_output_base_units")
                candidates=[output] if type(output)is int and 0<output<2**64 else []
                hypothetical=branch["hypothetical"]
                bounded=branch["source_bounded"]
            elif status in ("NATIVE_QUOTE_BOUNDED_NOT_EXACT","NATIVE_QUOTE_MODELED_NOT_EXACT"):
                envelope=q.get("native_fee_envelope")
                if not isinstance(envelope,dict) or any(
                        envelope.get(k)is not False for k in SAFE):
                    raise ValueError("unsafe source fee envelope")
                status_name=envelope.get("status","")
                if row["venue"]=="meteora_damm_v2":
                    low=envelope.get("lower_modeled_output")
                    high=envelope.get("upper_modeled_output")
                    hypothetical=True
                elif row["venue"]=="pumpswap":
                    low=envelope.get("minimum_candidate_output")
                    high=envelope.get("maximum_candidate_output")
                    hypothetical=True
                else:
                    low=envelope.get("lower_output_bound")
                    high=envelope.get("upper_output_bound")
                    hypothetical=branch["hypothetical"]
                if (type(low)is not int or type(high)is not int
                        or not 0<low<=high<2**64):
                    raise ValueError("invalid bound from native quote adapter")
                if envelope.get("source_slot")!=fixture["state_accounts_observed_slot"]:
                    raise ValueError("source fee envelope slot mismatch")
                if row["venue"]=="meteora_damm_v2" and "HYPOTHETICAL" not in status_name:
                    raise ValueError("unverified DAMM fee model incorrectly attested")
                candidates=list(dict.fromkeys((low,high)))
                bounded=True
            else:
                candidates=[]
            if not candidates:
                failures.append({"leg_index":index,"venue":row["venue"],
                                 "pool":row["address"],"amount":branch["amount"],
                                 "status":status,"reason":q.get("reason")})
                continue
            for output in candidates:
                following.append({"amount":output,
                    "trace":branch["trace"]+[{"leg_index":index,"venue":row["venue"],
                        "pool":row["address"],"amount_in":branch["amount"],
                        "amount_out":output,"source_slot":q["source_slot"],
                        "quote_status":status}],
                    "hypothetical":hypothetical,"source_bounded":bounded})
        if not following:
            return {"status":"MULTIHOP_NATIVE_SOURCE_INTERVAL_BLOCKED",
                "input_base_units":input_base_units,"blocked_leg_index":index,
                "failed_branches":failures,"completed_branches":[],
                "source_slot":fixture["state_accounts_observed_slot"],
                "full_route_quote_verified":False,"net_profit_verified":False,
                "signed_simulation_verified":False,**SAFE}
        # The next native quote may have discontinuous liquidity behavior;
        # preserve distinct branches up to a strict bounded search budget.
        if len(following)>max_branches:
            following=sorted(following,key=lambda b:b["amount"])
            following=following[:max_branches//2]+following[-(max_branches-max_branches//2):]
        branches=following
    outs=[branch["amount"] for branch in branches]
    return {"status":"MULTIHOP_SOURCE_SCENARIO_INTERVAL_NOT_EXACT",
        "route_hops":len(rows),
        "input_base_units":input_base_units,
        "minimum_modeled_output":min(outs),
        "maximum_modeled_output":max(outs),
        "minimum_modeled_gross_delta":min(outs)-input_base_units,
        "maximum_modeled_gross_delta":max(outs)-input_base_units,
        "hypothetical_fee_model_present":any(b["hypothetical"] for b in branches),
        "source_bounded_scenario_present":any(b["source_bounded"] for b in branches),
        "scenario_envelope_not_true_interval":any(b["hypothetical"] for b in branches),
        "completed_branches":branches,"failed_branches":failures,
        "source_slot":fixture["state_accounts_observed_slot"],
        "full_route_quote_verified":False,
        "estimated_cost_start_mint_base_units":None,
        "net_profit_verified":False,"signed_simulation_verified":False,**SAFE}
