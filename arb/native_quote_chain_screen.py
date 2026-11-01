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

def compare_quote_to_signed_spl(quote_report, signed_observations):
    """Compare independent exact-unit quoted outputs to signed CPI observations.

    This is strict numerical parity, not receipt/quote origin authentication.
    The signed CPI parser, pool source reader, and rollback verifier remain
    independent prerequisites; a matching pair of caller dicts proves none.
    """
    if (not isinstance(quote_report,dict)
        or quote_report.get("status")!="COMPLETE_QUOTE_CHAIN_ARITHMETIC_ONLY"
        or not isinstance(signed_observations,list)
        or len(signed_observations)!=len(quote_report.get("legs",[]))
        or not 2<=len(signed_observations)<=MAX_LEGS):
        raise ValueError("complete bounded native quote and CPI evidence required")
    diffs=[]
    for quote,observation in zip(quote_report["legs"],signed_observations):
        if (not isinstance(observation,dict)
            or observation.get("pool")!=quote["pool"]
            or observation.get("venue")!=quote["venue"]
            or observation.get("input_mint")!=quote["from"]
            or observation.get("output_mint")!=quote["to"]
            or observation.get("hop")!=quote["hop"]
            or type(observation.get("observed_input_base_units")) is not int
            or observation["observed_input_base_units"]!=quote["amount_in_base_units"]
            or type(observation.get("observed_output_base_units")) is not int
            or not 0<observation["observed_output_base_units"]<U64):
            raise ValueError("signed CPI leg disconnected, incomplete or wrong input")
        delta=observation["observed_output_base_units"]-quote["amount_out_base_units"]
        diffs.append({"hop":quote["hop"],"venue":quote["venue"],"pool":quote["pool"],
                      "native_minus_signed_output_base_units":-delta,
                      "signed_minus_native_output_base_units":delta,
                      "exact_parity":delta==0})
    return {"status":"QUOTE_SIGNED_SPL_NUMERICAL_PARITY_DIAGNOSTIC_ONLY",
            "all_legs_numerically_equal":all(x["exact_parity"] for x in diffs),
            "leg_comparisons":diffs,
            "signed_receipt_independently_authenticated_here":False,
            "native_quote_independently_authenticated_here":False,
            "net_profitability_verified":False,**SAFE}

def screen_fee_bounded_candidates(quote_reports, *, fee_upper_bound_base_units,
                                  maximum_candidates=20):
    """Rank only *hypothetical* start-mint surplus after a conservative fee cap.

    No route is declared profitable: fee cap is caller input, never a
    witnessed paid fee or a validated exchange-rate conversion. Unknown
    observations are rejected instead of being silently assigned zero fees.
    """
    if (not isinstance(quote_reports,list) or len(quote_reports)>10000
        or type(maximum_candidates) is not int or not 1<=maximum_candidates<=100
        or type(fee_upper_bound_base_units) is not int
        or not 0<=fee_upper_bound_base_units<U64):
        raise ValueError("bounded candidate screen and explicit fee upper bound required")
    candidates=[]
    for i,report in enumerate(quote_reports):
        if (not isinstance(report,dict)
            or report.get("status")!="COMPLETE_QUOTE_CHAIN_ARITHMETIC_ONLY"
            or report.get("native_quote_authenticity_established_here") is not False
            or report.get("signed_atomic_simulation_verified") is not False
            or report.get("net_profitability_verified") is not False
            or any(report.get(k) is not False for k in SAFE)
            or type(report.get("gross_quoted_delta_base_units")) is not int
            or not isinstance(report.get("start_mint"),str)
            or not isinstance(report.get("legs"),list)
            or not 2<=len(report["legs"])<=MAX_LEGS):
            raise ValueError("unqualified or fabricated quote candidate")
        if report["gross_quoted_delta_base_units"]<=fee_upper_bound_base_units:
            continue
        candidates.append({
            "candidate_index":i,
            "start_mint":report["start_mint"],
            "quoted_gross_delta_base_units":report["gross_quoted_delta_base_units"],
            "assumed_fee_upper_bound_base_units":fee_upper_bound_base_units,
            "hypothetical_surplus_base_units":
                report["gross_quoted_delta_base_units"]-fee_upper_bound_base_units,
            "verified_native_quote":False,"verified_actual_fee":False,
            "net_profitability_verified":False,**SAFE})
    candidates.sort(key=lambda c:(-c["hypothetical_surplus_base_units"],
                                   c["candidate_index"]))
    return {"status":"HYPOTHETICAL_FEE_CAPPED_QUOTE_SCREEN_NOT_PROFIT_EVIDENCE",
            "examined":len(quote_reports),
            "candidates_above_assumed_bound":len(candidates),
            "candidates":candidates[:maximum_candidates],
            "fee_bound_independently_verified":False,
            "net_profitability_verified":False,**SAFE}
