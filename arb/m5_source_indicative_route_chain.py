"""Source-account-bound indicative exact-input chaining for signed research leads.

An indicative native quote is useful for sizing/rejection even when protocol
rounding or execution parity is unverified. It is never net profitable or
execution-ready. Reuses existing all-seven signed native quote dispatcher.
"""
from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.fixture_all_venue_signed_quotes import quote_leg
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
def source_model_output(fixture,row,index,current,observed_unix,result,*,
                        allow_modeled_dlmm=False,allow_modeled_pumpswap=False):
    """Resolve only the existing source-selected research models, never exactness.

    Shared by route chaining and same-fixture fee conversion. Callers still
    validate the quote's outer pool, venue and source-slot identity.
    """
    if not isinstance(result,dict) or any(result.get(k) is not False for k in SAFE):
        raise ValueError("unsafe or malformed native leg quote")
    mints=fixture["route_mints"]
    status=result.get("quote_status")
    next_amount=result.get("predicted_output_base_units")
    modeled=False
    if (allow_modeled_dlmm and row["venue"]=="meteora_dlmm"
            and status=="NATIVE_QUOTE_SOURCE_DERIVED_NOT_EXACT"):
        envelope=result.get("native_fee_envelope")
        if not isinstance(envelope,dict):
            raise ValueError("missing source DLMM fee envelope")
        effective=envelope.get("source_derived_dynamic_fee_quote")
        if (envelope.get("pool")!=row["address"] or
                envelope.get("input_mint")!=mints[index] or
                envelope.get("output_mint")!=mints[index+1] or
                envelope.get("input_base_units")!=current or
                envelope.get("source_slot")!=fixture["state_accounts_observed_slot"] or
                not isinstance(effective,dict) or
                effective.get("status")!="SOURCE_VOLATILITY_DYNAMIC_FEE_MODELED" or
                effective.get("source_clock")!=observed_unix or
                effective.get("protocol_exact_verified") is not False or
                any(effective.get(k) is not False for k in SAFE)):
            raise ValueError("source DLMM modeled quote identity mismatch")
        next_amount=effective.get("amount_out")
        modeled=True
    if (allow_modeled_pumpswap and row["venue"]=="pumpswap"
            and status=="NATIVE_QUOTE_SELECTED_FEE_MODE_NOT_EXACT"):
        from arb.pumpswap_source_fee_envelope import selected_directional_model
        chosen=selected_directional_model(result.get("native_fee_envelope"))
        if chosen is not None:
            if (chosen["pool"]!=row["address"] or chosen["source_slot"]!=fixture["state_accounts_observed_slot"]
                    or chosen["input_mint"]!=mints[index] or chosen["output_mint"]!=mints[index+1]
                    or chosen["amount_in"]!=current or any(chosen.get(k) is not False for k in SAFE)):
                raise ValueError("PumpSwap modeled quote source identity mismatch")
            next_amount=chosen["amount_out"]
            modeled=True
    return status,next_amount,modeled

def research_chain(fixture, *, amount_in, observed_unix, allow_modeled_dlmm=False,
                   allow_modeled_pumpswap=False):
    if type(allow_modeled_dlmm) is not bool or type(allow_modeled_pumpswap) is not bool:
        raise ValueError("explicit modeled quote opt-in required")
    rows=extract_pool_states(fixture)
    if any(fixture.get(k) is not False for k in SAFE):
        raise ValueError("unsafe native route fixture")
    if not 2<=len(rows)<=6 or type(amount_in)is not int or not 0<amount_in<2**64:
        raise ValueError("valid source-bound route and initial input required")
    if type(observed_unix)is not int or observed_unix<0:
        raise ValueError("valid observation timestamp required")
    mints=fixture.get("route_mints")
    if not isinstance(mints,list) or len(mints)!=len(rows)+1 or mints[0]!=mints[-1]:
        raise ValueError("closed authenticated route mint topology required")
    if any(mints[i] not in row["mints"] or mints[i+1] not in row["mints"]
           for i,row in enumerate(rows)):
        raise ValueError("source account mint topology differs from route")
    current=amount_in
    trace=[]
    modeled_legs=0
    for index,row in enumerate(rows):
        result=quote_leg(fixture,leg_index=index,amount_in=current,
                         observed_unix=observed_unix)
        if not isinstance(result,dict) or any(result.get(k) is not False for k in SAFE):
            raise ValueError("unsafe or malformed native leg quote")
        status,next_amount,modeled=source_model_output(
            fixture,row,index,current,observed_unix,result,
            allow_modeled_dlmm=allow_modeled_dlmm,
            allow_modeled_pumpswap=allow_modeled_pumpswap)
        modeled_legs+=int(modeled)
        if status!="SOURCE_BOUND_INDICATIVE" and not modeled:
            return {"status":"NATIVE_ROUTE_INDICATIVE_BLOCKED",
                    "blocked_leg_index":index,"blocked_venue":row["venue"],
                    "reason":result.get("reason","source native quote missing")[:240],
                    "quoted_legs":trace,"full_route_quoted":False,
                    "signed_simulation_verified":False,"net_profit_verified":False,**SAFE}
        if (result.get("pool") not in (None,row["address"]) or
                result.get("venue") not in (None,row["venue"]) or
                result.get("source_slot")!=fixture.get("state_accounts_observed_slot")):
            raise ValueError("native quote source slot mismatch")
        if type(next_amount)is not int or not 0<next_amount<2**64:
            raise ValueError("invalid native predicted amount")
        trace.append({"index":index,"venue":row["venue"],"pool":row["address"],
                      "input_base_units":current,"output_base_units":next_amount,
                      "source_slot":result["source_slot"],"quote_status":status,
                      "uses_unverified_dynamic_fee_model":modeled})
        if row["venue"]=="orca" and "orca_directional_coverage" in result:
            trace[-1]["orca_directional_coverage"]=result["orca_directional_coverage"]
        if row["venue"]=="orca" and "orca_sparse_source_coverage" in result:
            trace[-1]["orca_sparse_source_coverage"]=result["orca_sparse_source_coverage"]
        current=next_amount
    return {"status":("SOURCE_BOUND_MODELED_CHAIN_NOT_EXECUTION_VERIFIED" if modeled_legs
                      else "SOURCE_BOUND_INDICATIVE_CHAIN_NOT_EXECUTION_VERIFIED"),
            "hops":len(rows),"input_base_units":amount_in,"output_base_units":current,
            "gross_delta_start_mint_base_units":current-amount_in,
            "estimated_cost_start_mint_base_units":None,
            "net_delta_start_mint_base_units":None,
            "net_economics_status":"UNCONVERTED_NETWORK_AND_PRIORITY_COSTS",
            "full_route_quoted":False,"indicative_all_legs":not bool(modeled_legs),
            "modeled_all_legs":bool(modeled_legs),"modeled_leg_count":modeled_legs,
            "protocol_exact_verified":False,
            "quoted_legs":trace,"signed_simulation_verified":False,
            "net_profit_verified":False,**SAFE}

def contextual_economic_model(fixture,*,amount_in):
    """Bound the pre-sign estimate to the original, nonhydrated Clock bytes.

    A missing SDK, blocked venue or divergent Clock must not prevent a
    separate genuine signed control attempt. Never promote modeled net.
    """
    from arb.next_ten_fork_pool_probe import contextual_pricing_clock
    from arb.source_snapshot_manifest import verify
    from arb.m5_signed_start_mint_economics import WSOL,source_native_fee_conversion
    verify(fixture)
    if (any(fixture.get(k) is not False for k in SAFE)
            or type(amount_in) is not int or not 0<amount_in<2**64):
        raise ValueError("safe source fixture and integer research amount required")
    mints=fixture["route_mints"]
    if not isinstance(mints,list) or not 3<=len(mints)<=7 or mints[0]!=mints[-1]:
        raise ValueError("closed source economic route required")
    clock=contextual_pricing_clock(fixture)
    base={"status":"PRIMARY_SOURCE_ECONOMICS_UNAVAILABLE","input_base_units":amount_in,
        "source_slot":fixture["state_accounts_observed_slot"],
        "manifest_sha256":fixture["state_account_manifest_sha256"],"start_mint":mints[0],
        "pricing_clock":clock,"output_base_units":None,"gross_delta":None,
        "estimated_message_fee_base_units":None,"estimated_net_delta":None,
        "message_fee_scenario_lamports":None,"source_native_fee_conversion":None,
        "priority_cost_included":False,"account_funding_included":False,
        "net_profit_verified":False,**SAFE}
    if clock is None:
        return {**base,"reason":"CONTEXTUAL_CLOCK_MODEL_UNAVAILABLE"}
    try:
        chain=research_chain(fixture,amount_in=amount_in,
            observed_unix=clock["clock"]["unix_timestamp"],
            allow_modeled_dlmm=True,allow_modeled_pumpswap=True)
    except (ValueError,RuntimeError,KeyError,TypeError,ArithmeticError,OSError) as exc:
        return {**base,"reason":"NATIVE_ROUTE_MODEL_UNAVAILABLE","error_class":type(exc).__name__}
    if not isinstance(chain,dict) or any(chain.get(k) is not False for k in SAFE):
        raise ValueError("unsafe contextual native economic model")
    if chain.get("status") not in ("SOURCE_BOUND_MODELED_CHAIN_NOT_EXECUTION_VERIFIED",
                                   "SOURCE_BOUND_INDICATIVE_CHAIN_NOT_EXECUTION_VERIFIED"):
        return {**base,"reason":"NATIVE_ROUTE_MODEL_BLOCKED","blocked_leg":chain.get("blocked_leg_index"),
                "blocked_venue":chain.get("blocked_venue"),"native_chain":chain}
    output=chain.get("output_base_units")
    if (type(output) is not int or not 0<output<2**64
            or chain.get("input_base_units")!=amount_in
            or chain.get("gross_delta_start_mint_base_units")!=output-amount_in
            or chain.get("signed_simulation_verified") is not False
            or chain.get("net_profit_verified") is not False):
        raise ValueError("invalid contextual native economic output")
    # Same explicit research fee assumption as existing Blockzilla grid.
    from arb.blockzilla_size_plan import MESSAGE_FEE_SCENARIO
    fee=MESSAGE_FEE_SCENARIO if mints[0]==WSOL else None
    conversion=None
    if mints[0]!=WSOL and WSOL in mints[1:-1]:
        fee,conversion,_=source_native_fee_conversion(fixture,start_mint=mints[0],
            source_slot=base["source_slot"],fee_lamports=MESSAGE_FEE_SCENARIO,
            observed_unix=clock["clock"]["unix_timestamp"])
    return {**base,"status":"PRIMARY_SOURCE_ECONOMIC_MODEL_ONLY",
        "message_fee_scenario_lamports":MESSAGE_FEE_SCENARIO,
        "source_native_fee_conversion":conversion,
        "native_chain":chain,"output_base_units":output,"gross_delta":output-amount_in,
        "estimated_message_fee_base_units":fee,
        "estimated_net_delta":output-amount_in-fee if fee is not None else None}


def main():
    import argparse,json
    from pathlib import Path
    p=argparse.ArgumentParser()
    p.add_argument("--fixture",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--amount",type=int,default=100000)
    p.add_argument("--observed-unix",type=int,required=True)
    a=p.parse_args()
    fixture=json.loads(Path(a.fixture).read_text())
    result=research_chain(fixture,amount_in=a.amount,observed_unix=a.observed_unix)
    Path(a.output).write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":result["status"],"hops":result.get("hops"),
                      "blocked_leg":result.get("blocked_leg_index"),
                      "signed_simulation_verified":False,"net_profit_verified":False,**SAFE}))
if __name__=="__main__":main()
