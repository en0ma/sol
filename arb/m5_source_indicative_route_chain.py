"""Source-account-bound indicative exact-input chaining for signed research leads.

An indicative native quote is useful for sizing/rejection even when protocol
rounding or execution parity is unverified. It is never net profitable or
execution-ready. Reuses existing all-seven signed native quote dispatcher.
"""
from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.fixture_all_venue_signed_quotes import quote_leg
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
def research_chain(fixture, *, amount_in, observed_unix):
    rows=extract_pool_states(fixture)
    if not 2<=len(rows)<=6 or type(amount_in)is not int or not 0<amount_in<2**64:
        raise ValueError("valid source-bound route and initial input required")
    if type(observed_unix)is not int or observed_unix<0:
        raise ValueError("valid observation timestamp required")
    mints=fixture.get("route_mints")
    if not isinstance(mints,list) or len(mints)!=len(rows)+1 or mints[0]!=mints[-1]:
        raise ValueError("closed authenticated route mint topology required")
    current=amount_in
    trace=[]
    for index,row in enumerate(rows):
        result=quote_leg(fixture,leg_index=index,amount_in=current,
                         observed_unix=observed_unix)
        status=result.get("quote_status")
        if status!="SOURCE_BOUND_INDICATIVE":
            return {"status":"NATIVE_ROUTE_INDICATIVE_BLOCKED",
                    "blocked_leg_index":index,"blocked_venue":row["venue"],
                    "reason":result.get("reason","source native quote missing")[:240],
                    "quoted_legs":trace,"full_route_quoted":False,
                    "signed_simulation_verified":False,"net_profit_verified":False,**SAFE}
        if result.get("source_slot")!=fixture.get("state_accounts_observed_slot"):
            raise ValueError("native quote source slot mismatch")
        next_amount=result.get("predicted_output_base_units")
        if type(next_amount)is not int or not 0<next_amount<2**64:
            raise ValueError("invalid native predicted amount")
        trace.append({"index":index,"venue":row["venue"],"pool":row["address"],
                      "input_base_units":current,"output_base_units":next_amount,
                      "source_slot":result["source_slot"]})
        current=next_amount
    return {"status":"SOURCE_BOUND_INDICATIVE_CHAIN_NOT_EXECUTION_VERIFIED",
            "hops":len(rows),"input_base_units":amount_in,"output_base_units":current,
            "gross_delta_start_mint_base_units":current-amount_in,
            "full_route_quoted":False,"indicative_all_legs":True,
            "quoted_legs":trace,"signed_simulation_verified":False,
            "net_profit_verified":False,**SAFE}
