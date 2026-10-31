"""Rank independently source-bound exact-input triangle quotes before signed trial.

This is a gross-only discovery ranking, not net profitability or execution
approval. Native missing fee/tick/bin accounts block a route explicitly.
"""
from arb.fixture_all_venue_signed_quotes import quote_leg

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def rank(fixtures, *, amount_in, observed_unix, maximum=30):
    if (not isinstance(fixtures,list) or len(fixtures)>100
            or type(amount_in)is not int or not 0<amount_in<2**64
            or type(observed_unix)is not int or observed_unix<0
            or type(maximum)is not int or not 1<=maximum<=100):
        raise ValueError("invalid bounded source quote ranking input")
    rows=[]
    for index,fixture in enumerate(fixtures):
        if not isinstance(fixture,dict):
            rows.append({"index":index,"status":"QUOTE_BLOCKED",
                         "reason":"source fixture malformed",**SAFE})
            continue
        venues=fixture.get("route_venues")
        mints=fixture.get("route_mints")
        if (not isinstance(venues,list) or len(venues)!=3
                or len(set(venues))!=3 or not isinstance(mints,list)
                or len(mints)!=4 or mints[0]!=mints[-1]):
            rows.append({"index":index,"status":"QUOTE_BLOCKED",
                         "reason":"not a closed distinct-venue triangle",**SAFE})
            continue
        amount=amount_in
        quotes=[]
        reason=None
        for leg_index in range(3):
            try:
                result=quote_leg(fixture,leg_index=leg_index,
                    amount_in=amount,observed_unix=observed_unix)
                if (not isinstance(result,dict)
                        or result.get("quote_status")!="SOURCE_BOUND_INDICATIVE"
                        or type(result.get("predicted_output_base_units"))is not int
                        or result["predicted_output_base_units"]<=0
                        or result.get("venue")!=venues[leg_index]
                        or result.get("pool")!=fixture["route_pool_addresses"][leg_index]
                        or result.get("source_slot")!=fixture["state_accounts_observed_slot"]):
                    raise ValueError(result.get("reason","source quote unavailable")
                                     if isinstance(result,dict) else "malformed source quote")
                amount=result["predicted_output_base_units"]
                quotes.append({"venue":result["venue"],"pool":result["pool"],
                               "input_mint":mints[leg_index],
                               "output_mint":mints[leg_index+1],
                               "amount_out":amount,"source_slot":result["source_slot"]})
            except (ValueError,KeyError,TypeError,ArithmeticError) as exc:
                reason="leg %d: %s"%(leg_index,str(exc)[:200])
                break
        if reason:
            rows.append({"index":index,"status":"QUOTE_BLOCKED",
                "quoted_legs":len(quotes),"reason":reason,**SAFE})
            continue
        rows.append({"index":index,"status":"GROSS_INDICATIVE_ONLY",
            "start_mint":mints[0],"input_base_units":amount_in,
            "output_base_units":amount,"gross_delta_start_mint_base_units":amount-amount_in,
            "positive_gross":amount>amount_in,"quotes":quotes,
            "cost_status":"UNVERIFIED_NETWORK_FEE_SLIPPAGE_AND_CONVERSION",
            "net_profitability_confirmed":False,**SAFE})
    ranked=sorted((r for r in rows if r["status"]=="GROSS_INDICATIVE_ONLY"),
                  key=lambda r:r["gross_delta_start_mint_base_units"],reverse=True)
    return {"status":"GROSS_SOURCE_BOUND_RANKING_ONLY",
        "fixtures_considered":len(rows),"fully_quoted":len(ranked),
        "blocked":len(rows)-len(ranked),
        "positive_gross":sum(r["positive_gross"] for r in ranked),
        "net_profitable_candidates":0,"ranked":ranked[:maximum],
        "all_results":rows,**SAFE}
