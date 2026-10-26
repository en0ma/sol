"""Venue-owned research quoting; no coordinator-specific fee or math logic.

Each implementation enforces venue-specific state prerequisites. A missing
tick/bin/dynamic fee is a blocked quote, never a default rate or executable
trade. All outputs are independent, indicative and simulation-only.
"""
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def quote(venue,state,input_mint,amount,*,evidence=None):
    if type(amount) is not int or not 0<amount<2**64:
        raise ValueError("invalid exact-input amount")
    if not isinstance(state,dict) or not isinstance(evidence,dict):
        raise ValueError("venue state and authenticated pricing evidence required")
    if evidence.get("source_authenticated") is not True:
        raise ValueError("unverified venue pricing evidence")
    if venue=="orca":
        from arb.orca_spot_quote import quote_bounded_single_tick
        bounds=evidence["current_tick_sqrt_bounds_x64"]
        if not evidence.get("tick_bounds_authenticated") is True:
            raise ValueError("Orca tick boundaries not source-authenticated")
        native=quote_bounded_single_tick(state,input_mint,amount,
            lower_sqrt_x64=bounds[0],upper_sqrt_x64=bounds[1])
    elif venue=="raydium_clmm":
        from arb.raydium_clmm_within_tick_quote import quote_within_tick
        if not evidence.get("next_initialized_tick_authenticated") is True:
            raise ValueError("CLMM next initialized tick not authenticated")
        native=quote_within_tick(state,input_mint,amount,
            evidence["trade_fee_ppm"],evidence["next_initialized_sqrt_price_x64"])
    elif venue=="meteora_dlmm":
        raise ValueError("DLMM active-bin liquidity and dynamic fee traversal not authenticated")
    elif venue=="meteora_damm_v2":
        raise ValueError("DAMM v2 dynamic fee and liquidity range not authenticated")
    elif venue=="pumpswap":
        from arb.pumpswap_quote import quote_exact_input
        if evidence.get("effective_fee_verified") is not True:
            raise ValueError("PumpSwap effective fee tier unauthenticated")
        native=quote_exact_input(state,input_mint,amount,
            verified_total_fee_ppm=evidence["effective_total_fee_ppm"])
    elif venue in ("raydium_cpmm","raydium_amm_v4"):
        raise ValueError("use authenticated CPMM / AMM v4 fixture-native quote adapters")
    else:
        raise ValueError("unknown venue")
    output=native.get("estimated_output_base_units")
    if type(output) is not int or output<=0:
        raise ValueError("venue returned invalid integer output")
    return {"venue":venue,"input_mint":input_mint,"amount_in":amount,
            "amount_out":output,"venue_quote":native,
            "protocol_exact_verified":False,**SAFE}
