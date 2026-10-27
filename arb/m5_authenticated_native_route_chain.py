"""Fail-closed exact-input chaining for authenticated 2–6-hop source routes.

Each leg must produce a separately authenticated same-slot native quote.
No synthetic prices, decimals conversions, profitability inference or broadcast.
"""
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
def chain(route, *, initial_input, quote_leg):
    if (not isinstance(route,dict) or type(initial_input)is not int
            or not 0<initial_input<2**64 or not callable(quote_leg)):
        raise ValueError("invalid authenticated multihop quote request")
    legs=route.get("legs")
    if not isinstance(legs,list) or not 2<=len(legs)<=6 or route.get("hops")!=len(legs):
        raise ValueError("authenticated 2–6-hop route required")
    origin=route.get("start_mint")
    if not isinstance(origin,str) or not origin:
        raise ValueError("starting mint required")
    current=origin
    for leg in legs:
        if (not isinstance(leg,dict) or leg.get("input")!=current or
                not leg.get("output") or not leg.get("pool") or not leg.get("venue")):
            raise ValueError("source route mint/venue/pool discontinuity")
        current=leg["output"]
    if current!=origin:
        raise ValueError("source route must close at starting mint")
    observed_slot=None
    amount=initial_input
    trace=[]
    for index,leg in enumerate(legs):
        q=quote_leg(leg,amount)
        if not isinstance(q,dict) or any(q.get(k) is not False for k in SAFE):
            raise ValueError("native leg safety proof missing")
        if (q.get("pool")!=leg["pool"] or q.get("venue")!=leg["venue"] or
                q.get("input_mint")!=leg["input"] or
                q.get("output_mint")!=leg["output"] or
                q.get("amount_in")!=amount or
                q.get("source_authenticated") is not True or
                q.get("source_quote_verified") is not True or
                q.get("protocol_exact_verified") is not True):
            raise ValueError("native leg source/exact-quote binding unavailable")
        slot=q.get("snapshot_slot")
        output=q.get("amount_out")
        if (type(slot)is not int or slot<0 or
                type(output)is not int or not 0<output<2**64 or
                (observed_slot is not None and slot!=observed_slot)):
            raise ValueError("native leg amount/slot invalid or unsynchronized")
        observed_slot=slot
        trace.append({"index":index,"venue":leg["venue"],"pool":leg["pool"],
                      "input_mint":leg["input"],"output_mint":leg["output"],
                      "amount_in":amount,"amount_out":output,"snapshot_slot":slot})
        amount=output
    return {"status":"SOURCE_NATIVE_CHAIN_QUOTED_NOT_EXECUTION_VERIFIED",
            "start_mint":origin,"initial_input":initial_input,"final_output":amount,
            "gross_delta_start_mint_units":amount-initial_input,
            "net_profit_verified":False,"signed_simulation_verified":False,
            "snapshot_slot":observed_slot,"legs":trace,**SAFE}
