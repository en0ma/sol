"""Conservative single-tick indicative Orca Whirlpool quotes for discovery.

Uses verified Whirlpool sqrt price, liquidity, and fee; deliberately rejects
tick crossings rather than inventing a multi-tick quote. For candidate ranking
only, never authorizes execution or profitability claims.
"""
from arb.orca_whirlpool import fetch_pool
from arb.whirlpool_preflight import verify_oracle
Q=1<<64
FEE_DENOM=1_000_000

def quote_single_tick(state,mint_in,amount_in):
    if type(amount_in)is not int or not 0<amount_in<1<<64:
        raise ValueError("invalid amount")
    a,b=state["token_mint_a"],state["token_mint_b"]
    if mint_in not in (a,b):raise ValueError("mint not in pool")
    L=int(state["liquidity"]);p=int(state["sqrt_price_x64"])
    fee=state["fee_rate_hundredths_bps"]
    if L<=0 or p<=0 or type(fee)is not int or not 0<=fee<FEE_DENOM:
        raise ValueError("invalid liquidity, price or fee")
    effective=amount_in*(FEE_DENOM-fee)//FEE_DENOM
    if effective<=0:raise ValueError("amount eaten by fees")
    if mint_in==a:
        next_p=(L*Q*p+(L*Q+effective*p)-1)//(L*Q+effective*p)
        output=L*(p-next_p)//Q
    else:
        next_p=p+effective*Q//L
        output=L*Q*(next_p-p)//(p*next_p)
    if next_p<=0 or output<=0:raise ValueError("dust quote")
    return {"mint_in":mint_in,"mint_out":b if mint_in==a else a,
            "amount_in":amount_in,"estimated_output_base_units":output,
            "fee_rate_ppm":fee,"post_sqrt_price_x64":str(next_p),
            "tick_boundary_verified":False,"status":"INDICATIVE_SPOT_ONLY",
            "actionable":False,"executable_quote":False}

def quote_pool_state(state,mint_in,amount_in):
    return quote_single_tick(state,mint_in,amount_in)


def quote_bounded_single_tick(state, mint_in, amount_in, *, lower_sqrt_x64, upper_sqrt_x64):
    """Bound an indicative swap using caller-supplied current tick edges.

    The caller must independently verify both prices and their association with the
    current initialized tick. This does NOT traverse tick arrays or assert that
    execution matches this arithmetic.
    """
    if type(lower_sqrt_x64) is not int or type(upper_sqrt_x64) is not int:
        raise ValueError("tick bounds must be integer prices")
    p=int(state["sqrt_price_x64"])
    if not 0<lower_sqrt_x64<=p<upper_sqrt_x64:
        raise ValueError("invalid or stale current tick bounds")
    q=quote_single_tick(state,mint_in,amount_in)
    next_p=int(q["post_sqrt_price_x64"])
    if not lower_sqrt_x64<next_p<upper_sqrt_x64:
        raise ValueError("quote would reach or cross a tick boundary")
    return {**q, "supplied_tick_boundary_checked":True,
            "status":"INDICATIVE_WITHIN_SUPPLIED_TICK",
            "actionable":False,"executable_quote":False}

def maximum_bounded_input(state, mint_in, *, lower_sqrt_x64, upper_sqrt_x64,
                          max_input, iterations=64):
    """Search a bounded integer size range for a strictly in-tick indicative quote.

    Feasible amounts must be monotone for the constant-liquidity model.
    Exact boundary hits are rejected. Neither these bounds nor quote outputs
    are independently verified by this search; no execution is authorized.
    """
    if type(max_input) is not int or not 0<max_input<1<<64:
        raise ValueError("invalid maximum input budget")
    if type(iterations) is not int or not 1<=iterations<=64:
        raise ValueError("invalid search budget")
    if type(lower_sqrt_x64) is not int or type(upper_sqrt_x64) is not int:
        raise ValueError("invalid tick boundary types")
    p=int(state["sqrt_price_x64"])
    if not 0<lower_sqrt_x64<=p<upper_sqrt_x64:
        raise ValueError("invalid current tick bounds")
    # Validate mint, fee, and liquidity even if the smallest amount is dust.
    if mint_in not in (state["token_mint_a"],state["token_mint_b"]):
        raise ValueError("input mint missing from pool")
    if int(state["liquidity"])<=0 or type(state["fee_rate_hundredths_bps"]) is not int or not 0<=state["fee_rate_hundredths_bps"]<FEE_DENOM:
        raise ValueError("invalid pool liquidity or fee")

    lo,hi=0,max_input
    best=None
    probes=0
    while lo<hi and probes<iterations:
        middle=(lo+hi+1)//2
        probes+=1
        try:
            quote=quote_bounded_single_tick(
                state,mint_in,middle,
                lower_sqrt_x64=lower_sqrt_x64,
                upper_sqrt_x64=upper_sqrt_x64)
        except ValueError as exc:
            # Only price/dust limitations imply a smaller trade may work.
            if str(exc) not in ("quote would reach or cross a tick boundary",
                                "dust quote","amount eaten by fees"):
                raise
            if str(exc) in ("dust quote","amount eaten by fees"):
                # Dust means this amount is too small; it is not a safe upper bound.
                lo=middle
                continue
            hi=middle-1
        else:
            lo=middle
            best=quote
    # Never describe a partial search as a maximum. With dust at the lower
    # bound, the feasible interval is not a simple true-then-false predicate;
    # the maximum is therefore unknown until feasibility is established.
    if lo!=hi:
        return {"status":"INCOMPLETE_SIZE_SEARCH","max_tested_input_base_units":None,
                "quote":None,"probes":probes,"search_converged":False,
                "actionable":False,"executable_quote":False}
    # Recheck the final tested amount rather than treating convergence as proof.
    if lo>0:
        try:
            best=quote_bounded_single_tick(
                state,mint_in,lo,lower_sqrt_x64=lower_sqrt_x64,
                upper_sqrt_x64=upper_sqrt_x64)
        except ValueError:
            best=None
    return {"status":"INDICATIVE_SIZE_BOUND" if best else "NO_BOUNDED_QUOTE",
            "max_tested_input_base_units":lo if best else None,
            "quote":best,"probes":probes,
            "search_converged":lo==hi,
            "actionable":False,"executable_quote":False}


def quote_inside_observed_absent_array(state,mint_in,amount_in,*,pool,fixture):
    """Static-fee research only; original null PDA is not a synthetic tick array."""
    from arb.whirlpool_ticks import verify_sparse_tick_fixture,start_tick,MAX_TICK,ARRAY_TICKS
    from arb.orca_tick_math import sqrt_price_from_tick_index
    from arb.fixture_quote_execution_pipeline import extract_pool_states
    if any(fixture.get(k) is not False for k in ("actionable","broadcast","live_execution_approved")):
        raise ValueError("unsafe sparse Whirlpool quote fixture")
    verify_sparse_tick_fixture(fixture)
    rows=extract_pool_states(fixture)
    matches=[(i,row) for i,row in enumerate(rows) if row["address"]==pool and row["venue"]=="orca"]
    if len(matches)!=1:
        raise ValueError("sparse Whirlpool pool identity ambiguous")
    i,row=matches[0]
    if row["decoded_pool_state"]!=state or fixture["route_mints"][i]!=mint_in:
        raise ValueError("sparse Whirlpool decoded pool/direction differs")
    proof=fixture["leg_evidence_by_index"][i]["auxiliary"].get("sparse_tick_source")
    if (not isinstance(proof,dict) or proof["ordered_arrays"][0] not in proof["absent_arrays"]
            or state["fee_tier_index_seed"]!=state["tick_spacing"]):
        raise ValueError("static sparse current array absence required")
    spacing=state["tick_spacing"];current=state["tick_current_index"]
    start=start_tick(current,spacing)
    low=max(-MAX_TICK,start)
    high=min(MAX_TICK,start+(ARRAY_TICKS-1)*spacing)
    if not low<high:
        raise ValueError("empty sparse array has no bounded price interval")
    # Keep the final price strictly inside the current observed array. No
    # assumption about another array, tick crossing or adaptive fee update.
    lower=sqrt_price_from_tick_index(low);upper=sqrt_price_from_tick_index(high)
    native=quote_bounded_single_tick(state,mint_in,amount_in,
        lower_sqrt_x64=lower,upper_sqrt_x64=upper)
    return {**native,"source":"OBSERVED_ABSENT_CURRENT_ARRAY_STATIC_BOUNDED",
        "ticks_crossed":0,"sparse_source_coverage":{"source_slot":row["snapshot_slot"],
            "present_contiguous_array_starts":[],"observed_absent_arrays":proof["absent_arrays"],
            "current_array_start":start,"bounded_tick_interval":[low,high],
            "absent_arrays_crossed":False,"protocol_exact_verified":False}}
