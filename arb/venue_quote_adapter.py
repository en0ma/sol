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
        from arb.meteora_dlmm_bin_quote import quote_one_bin
        if (evidence.get("bin_state_authenticated") is not True or
                evidence.get("effective_dynamic_fee_authenticated") is not True or
                state.get("snapshot_slot")!=evidence.get("bin_snapshot_slot")
                or state.get("snapshot_slot")!=evidence.get("fee_snapshot_slot")):
            raise ValueError("DLMM bin state and dynamic fee must share source slot")
        x=quote_one_bin(amount_in=amount,
            swap_x_for_y=input_mint==state["token_x_mint"],
            price_q64=evidence["active_bin_price_q64"],
            bin_x=evidence["active_bin_amount_x"],
            bin_y=evidence["active_bin_amount_y"],
            total_fee_rate=evidence["total_fee_rate"],
            active_bin_id=state["active_id"],
            observed_bin_id=evidence["active_bin_id"])
        if input_mint not in (state["token_x_mint"],state["token_y_mint"]):
            raise ValueError("DLMM mint not in pool")
        native={"estimated_output_base_units":x["amount_out"],**x}
    elif venue=="meteora_damm_v2":
        from arb.meteora_damm_v2_quote import quote_exact_input
        if (evidence.get("dynamic_fee_authenticated") is not True or
                evidence.get("fee_collection_mode_authenticated") is not True or
                state.get("snapshot_slot")!=evidence.get("fee_snapshot_slot")
                or evidence.get("range_curve_compatible") is not True):
            raise ValueError("DAMM fee and curve provenance unavailable")
        if input_mint not in (state["token_a_mint"],state["token_b_mint"]):
            raise ValueError("DAMM input mint not in pool")
        x=quote_exact_input(state["vault_base_units"][0],state["vault_base_units"][1],
            amount,input_is_a=input_mint==state["token_a_mint"],
            effective_fee_ppm=evidence["effective_fee_ppm"],
            fee_token_side=evidence["fee_token_side"])
        native={"estimated_output_base_units":x["amount_out"],**x}
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

def quote_concentrated_source_bound(venue,state,input_mint,amount,*,snapshot_slot,
                                    bounds_slot,fee_slot=None,
                                    lower_sqrt_x64=None,upper_sqrt_x64=None,
                                    next_initialized_sqrt_price_x64=None,trade_fee_ppm=None):
    """Quote only if curve bounds and fee belong to the SAME pool-state slot.

    Synthetic or stale tick boundaries cannot become authenticated by passing
    a boolean. The caller must have actually decoded these from venue-owned
    tick arrays; this gate only checks the provenance agreement.
    """
    if type(snapshot_slot)is not int or type(bounds_slot)is not int or snapshot_slot<0:
        raise ValueError("source slot missing")
    if snapshot_slot!=bounds_slot:
        raise ValueError("tick bounds are stale relative to pool")
    if venue=="orca":
        e={"source_authenticated":True,"tick_bounds_authenticated":True,
           "current_tick_sqrt_bounds_x64":[lower_sqrt_x64,upper_sqrt_x64]}
    elif venue=="raydium_clmm":
        if fee_slot!=snapshot_slot:
            raise ValueError("CLMM fee configuration from different slot")
        e={"source_authenticated":True,"next_initialized_tick_authenticated":True,
           "trade_fee_ppm":trade_fee_ppm,
           "next_initialized_sqrt_price_x64":next_initialized_sqrt_price_x64}
    else:raise ValueError("concentrated liquidity venue required")
    r=quote(venue,state,input_mint,amount,evidence=e)
    return {**r,"source_snapshot_slot":snapshot_slot,
            "tick_state_same_slot_checked":True,"protocol_exact_verified":False}

def quote_pumpswap_source_bound(state,input_mint,amount,*,pool_slot,fee_slot,
                                effective_total_fee_ppm,fee_tier_provenance):
    """Use PumpSwap's existing virtual-reserve/fee-bucket engine, not CPMM math.

    Requires an independently decoded, synchronized effective fee tier.
    The pool and fee configuration must already have undergone owner/byte
    authentication upstream; never substitute a static venue-wide rate.
    """
    if (type(pool_slot)is not int or pool_slot<0 or
            type(fee_slot)is not int or pool_slot!=fee_slot):
        raise ValueError("PumpSwap pool and dynamic fee config snapshots differ")
    if fee_tier_provenance!="SOURCE_DECODED_EFFECTIVE_TIER":
        raise ValueError("PumpSwap effective fee tier lacks native provenance")
    if (state.get("verified") is not True or
            state.get("fee_verified_onchain") is not True or
            state.get("effective_fee_verified") is not True):
        raise ValueError("PumpSwap state lacks independent fee authentication")
    return {**quote("pumpswap",state,input_mint,amount,evidence={
        "source_authenticated":True,"effective_fee_verified":True,
        "effective_total_fee_ppm":effective_total_fee_ppm}),
        "pool_and_fee_snapshot_slot":pool_slot,
        "fee_tier_provenance":fee_tier_provenance}
