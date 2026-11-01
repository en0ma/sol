"""Fail-closed, exact-raw-unit diagnostic for a bounded quoted graph route.

Each quote must be independently retrieved by the caller from a specific,
owner-verified native pool state. This checker only reconciles typed quantities
and pool identity; it cannot establish the origin or accuracy of quotes, and
must never mark the resulting opportunity as net profitable or actionable.
"""
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
U64=2**64
MAX_LEGS=6

def check_quote_chain(route, quotes, *, initial_base_units, min_output_base_units=1):
    """Reject partial, disconnected, stale, or inconsistent pool quote chains."""
    if (not isinstance(route,dict) or not isinstance(quotes,list)
        or type(initial_base_units) is not int or not 0<initial_base_units<U64
        or type(min_output_base_units) is not int
        or not 0<min_output_base_units<U64):
        raise ValueError("bounded exact-unit quote inputs required")
    legs=route.get("legs")
    if (not isinstance(legs,list) or not 2<=len(legs)<=MAX_LEGS
        or len(quotes)!=len(legs)):
        raise ValueError("complete 2..6-leg quote inventory required")
    first=legs[0].get("from") if isinstance(legs[0],dict) else None
    if not isinstance(first,str) or len(first)<32:
        raise ValueError("canonical start mint required")
    current_mint=first
    amount=initial_base_units
    rows=[]
    slots=set()
    for index,(leg,quote) in enumerate(zip(legs,quotes)):
        if not isinstance(leg,dict) or not isinstance(quote,dict):
            raise ValueError("invalid quote or leg")
        if (leg.get("from")!=current_mint
            or not isinstance(leg.get("to"),str) or len(leg["to"])<32
            or not isinstance(leg.get("pool"),str) or not leg["pool"]
            or not isinstance(leg.get("venue"),str) or not leg["venue"]
            or quote.get("venue")!=leg["venue"]
            or quote.get("pool")!=leg["pool"]
            or quote.get("input_mint")!=current_mint
            or quote.get("output_mint")!=leg["to"]):
            raise ValueError("quote disagrees with canonical connected pool leg")
        incoming=quote.get("amount_in_base_units")
        outgoing=quote.get("amount_out_base_units")
        fee=quote.get("swap_fee_input_base_units")
        slot=quote.get("source_slot")
        if (type(incoming) is not int or incoming!=amount
            or type(outgoing) is not int or not 0<outgoing<U64
            or type(fee) is not int or not 0<=fee<incoming
            or type(slot) is not int or slot<0):
            raise ValueError("missing, invalid, or mismatched exact quote amount")
        if quote.get("native_quote_origin_independently_verified") is not True:
            raise ValueError("independent native quote provenance unavailable")
        slots.add(slot)
        rows.append({"hop":index+1,"venue":leg["venue"],"pool":leg["pool"],
                     "from":current_mint,"to":leg["to"],"amount_in_base_units":incoming,
                     "amount_out_base_units":outgoing,
                     "swap_fee_input_base_units":fee,"source_slot":slot})
        current_mint=leg["to"]
        amount=outgoing
    if current_mint!=first:
        raise ValueError("route must close in exact canonical start mint")
    if len(slots)!=1:
        raise ValueError("cross-slot quote state is not a coherent snapshot")
    gross=amount-initial_base_units
    return {"status":"COMPLETE_QUOTE_CHAIN_ARITHMETIC_ONLY",
            "source_slot":next(iter(slots)),"start_mint":first,
            "initial_base_units":initial_base_units,
            "terminal_quoted_base_units":amount,
            "gross_quoted_delta_base_units":gross,
            "gross_quote_above_floor":amount>=min_output_base_units,
            "legs":rows,"native_quote_authenticity_established_here":False,
            "signed_atomic_simulation_verified":False,
            "net_profitability_verified":False,
            "actual_paid_network_fees_verified":False,**SAFE}
