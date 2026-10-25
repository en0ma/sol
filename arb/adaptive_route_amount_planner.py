"""Venue-independent sequential exact-input preflight planning for 2–6 legs.

Each following amount comes only from the preceding signed offline observed
SPL output. The graph is rebuilt and signed afterward; observed preflights
alone do not prove exact atomic flow or rollback and cannot authorize trading.
"""
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
def plan(legs,first_input,observe,*,require_closed=True):
    if not isinstance(legs,(tuple,list)) or not 2<=len(legs)<=6:
        raise ValueError("2-6 legs required")
    if type(first_input)is not int or not 0<first_input<2**64 or not callable(observe):
        raise ValueError("invalid input or signed offline observer")
    amounts=[]; evidence=[]; current=first_input
    for i,leg in enumerate(legs):
        if not isinstance(leg,dict) or not all(isinstance(leg.get(k),str) and leg[k] for k in ("venue","pool","input_mint","output_mint")):
            raise ValueError("invalid graph leg")
        if i and legs[i-1]["output_mint"]!=leg["input_mint"]:
            raise ValueError("disconnected graph")
        amounts.append(current)
        result=observe(i,leg,current)
        if not isinstance(result,dict) or result.get("signed_offline_observed") is not True:
            raise ValueError("missing signed standalone observation")
        output=result.get("output_base_units")
        if type(output)is not int or not 0<output<2**64:
            raise ValueError("invalid signed observed output")
        evidence.append({"index":i,"venue":leg["venue"],"pool":leg["pool"],
                         "amount_in":current,"observed_output":output})
        current=output
    if require_closed and legs[0]["input_mint"]!=legs[-1]["output_mint"]:
        raise ValueError("route is not closed")
    return {"status":"SIGNED_PREFLIGHT_AMOUNTS_ONLY","amounts":amounts,
            "observations":evidence,"atomic_execution_verified":False,
            "quote_accuracy_verified":False,**SAFE}
