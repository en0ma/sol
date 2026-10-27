"""Sweep genuine authenticated 4–6-hop native route amounts before signing.

Reuses the one existing venue-owned quote dispatcher. Per-leg blockers remain
visible across the amount sweep even if the first leg fails. No synthetic
liquidity, no net-profit labels, no live execution.
"""
from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.fixture_all_venue_signed_quotes import quote_leg
from arb.m5_source_indicative_route_chain import research_chain
from arb.m5_source_multihop_interval_engine import walk
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def sweep(fixture, *, observed_unix, amounts=(10000,100000,1000000)):
    rows=extract_pool_states(fixture)
    if (not 4<=len(rows)<=6 or
            not isinstance(amounts,(tuple,list)) or not 1<=len(amounts)<=8 or
            any(type(x)is not int or not 0<x<2**64 for x in amounts) or
            any(fixture.get(k)is not False for k in SAFE)):
        raise ValueError("safe four-to-six-hop source amount sweep required")
    attempts=[]
    venue_probes=[]
    modeled_intervals=[]
    for amount in amounts:
        result=research_chain(fixture,amount_in=amount,observed_unix=observed_unix)
        modeled=walk(fixture,input_base_units=amount,observed_unix=observed_unix)
        modeled_intervals.append({"input_base_units":amount,"status":modeled["status"],
            "minimum_modeled_output":modeled.get("minimum_modeled_output"),
            "maximum_modeled_output":modeled.get("maximum_modeled_output"),
            "hypothetical_fee_model_present":modeled.get("hypothetical_fee_model_present"),
            "full_route_quote_verified":False,**SAFE})
        attempts.append({"input_base_units":amount,"status":result["status"],
            "quoted_leg_count":len(result.get("quoted_legs",[])),
            "blocked_leg_index":result.get("blocked_leg_index"),
            "blocked_venue":result.get("blocked_venue"),
            "gross_delta_start_mint_base_units":result.get("gross_delta_start_mint_base_units"),
            "indicative_gross_positive":(result.get("gross_delta_start_mint_base_units",0)>0
                if result.get("indicative_all_legs") is True else None),
            "estimated_cost_start_mint_base_units":None,
            "net_delta_start_mint_base_units":None,
            "net_profit_verified":False,**SAFE})
        for i,row in enumerate(rows):
            q=quote_leg(fixture,leg_index=i,amount_in=amount,observed_unix=observed_unix)
            if not isinstance(q,dict) or any(q.get(k)is not False for k in SAFE):
                raise ValueError("unsafe individual native venue quote")
            venue_probes.append({"venue":row["venue"],"pool":row["address"],
                "leg_index":i,"input_base_units":amount,
                "quote_status":q.get("quote_status"),
                "reason":q.get("reason"),"protocol_exact_verified":False,**SAFE})
    completed=[x for x in attempts if x["indicative_gross_positive"] is not None]
    ranked=sorted(completed,key=lambda x:(-x["gross_delta_start_mint_base_units"],x["input_base_units"]))
    return {"status":"SOURCE_FOUR_TO_SIX_HOP_NATIVE_SWEEP_INDICATIVE_ONLY",
            "hops":len(rows),"source_slot":fixture["state_accounts_observed_slot"],
            "route_venues":[row["venue"] for row in rows],
            "attempt_count":len(attempts),"venue_probe_count":len(venue_probes),
            "attempts":attempts,"venue_probes":venue_probes,
            "source_native_multihop_modeled_intervals":modeled_intervals,
            "complete_indicative_chain_count":len(completed),
            "indicative_positive_gross_count":sum(x["indicative_gross_positive"] for x in completed),
            "indicative_ranked_input_sizes":[x["input_base_units"] for x in ranked],
            "protocol_exact_route_count":0,"net_profitable_route_count":0,
            "independently_signed_verified":False,**SAFE}

def main():
    import argparse,json
    from pathlib import Path
    p=argparse.ArgumentParser()
    p.add_argument("--fixture",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--observed-unix",required=True,type=int)
    p.add_argument("--amounts",default="10000,100000,1000000")
    a=p.parse_args()
    result=sweep(json.loads(Path(a.fixture).read_text()),
                 observed_unix=a.observed_unix,
                 amounts=tuple(int(x) for x in a.amounts.split(",")))
    Path(a.output).write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":result["status"],
       "attempt_count":result["attempt_count"],"venue_probe_count":result["venue_probe_count"],
       "protocol_exact_route_count":0,"broadcast":False}))
if __name__=="__main__":main()
