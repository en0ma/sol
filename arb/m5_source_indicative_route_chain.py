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
    if any(mints[i] not in row["mints"] or mints[i+1] not in row["mints"]
           for i,row in enumerate(rows)):
        raise ValueError("source account mint topology differs from route")
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
        if (result.get("pool") not in (None,row["address"]) or
                result.get("venue") not in (None,row["venue"]) or
                result.get("source_slot")!=fixture.get("state_accounts_observed_slot")):
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
            "estimated_cost_start_mint_base_units":None,
            "net_delta_start_mint_base_units":None,
            "net_economics_status":"UNCONVERTED_NETWORK_AND_PRIORITY_COSTS",
            "full_route_quoted":False,"indicative_all_legs":True,
            "quoted_legs":trace,"signed_simulation_verified":False,
            "net_profit_verified":False,**SAFE}

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
