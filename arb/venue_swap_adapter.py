"""Venue-specific swap adapter: delegate instruction encoding to existing builders.

The atomic graph coordinator NEVER branches on DEX-specific layouts. Adapter
preflights pool/mint direction and delegates to the already-implemented
standalone swap builders, including PumpSwap's exact-input instructions.
No broadcasting or authorizing live execution.
"""
def build_leg(venue,pool,state,evidence,owner,src,dst,
              mint_in,mint_out,amount,floor):
    if not (type(amount) is int and type(floor) is int and 0<amount<2**64 and 0<floor<2**64):
        raise ValueError("invalid nonzero swap amount")
    if venue=="meteora_damm_v2":
        from arb.meteora_damm_v2_swap import build_swap2
        if (mint_in,mint_out) not in (
            (state["token_a_mint"],state["token_b_mint"]),
            (state["token_b_mint"],state["token_a_mint"])):
            raise ValueError("DAMM pair mismatch")
        return build_swap2(pool,state,owner,src,dst,amount,floor,
                           input_is_a=mint_in==state["token_a_mint"])
    if venue=="raydium_cpmm":
        from arb.raydium_swap import instruction
        if (mint_in,mint_out) not in (
            (state["token_0_mint"],state["token_1_mint"]),
            (state["token_1_mint"],state["token_0_mint"])):
            raise ValueError("CPMM pair mismatch")
        return instruction(pool,state,owner,src,dst,amount,floor,
                           input_is_token_0=mint_in==state["token_0_mint"],
                           expected_mints=None)
    if venue=="orca":
        from arb.whirlpool_swap import build_swap
        from arb.whirlpool_swap import select_tick_arrays
        from arb.whirlpool_preflight import verify_oracle
        a,b=state["token_mint_a"],state["token_mint_b"]
        if (mint_in,mint_out) not in ((a,b),(b,a)):
            raise ValueError("Orca pair mismatch")
        oracle=evidence["oracle"]
        arrays=select_tick_arrays(pool,state["tick_current_index"],
                                  state["tick_spacing"],mint_in==a)
        if not set(arrays).issubset(set(evidence["tick_arrays"])):
            raise ValueError("unauthenticated Orca tick array")
        # Orca accounts are always A/B order, regardless of input direction.
        user_a,user_b=(src,dst) if mint_in==a else (dst,src)
        return build_swap(pool,state,owner,user_a,user_b,oracle,amount,floor,
                          a_to_b=mint_in==a,amount_specified_is_input=True,
                          oracle_writable=state["tick_spacing"]!=state["fee_tier_index_seed"])
    if venue=="meteora_dlmm":
        from arb.meteora_dlmm_swap import build_swap
        x,y=state["token_x_mint"],state["token_y_mint"]
        if (mint_in,mint_out) not in ((x,y),(y,x)):
            raise ValueError("DLMM pair mismatch")
        bins=evidence.get("bin_arrays")
        if not bins or not isinstance(bins,list):
            raise ValueError("authenticated DLMM bins unavailable")
        enriched=dict(state,input_mint=mint_in,output_mint=mint_out)
        return build_swap(pool,enriched,owner,src,dst,state["oracle"],bins,
                          amount,floor,input_is_x=mint_in==x,
                          bitmap_extension=state.get("bitmap_extension"))
    if venue=="pumpswap":
        # Reuse the existing PumpSwap *exact-input* buy_exact_quote_in /
        # sell transaction builder. Its internally different wire formats
        # are not an atomic coordinator responsibility.
        from arb.pumpswap_instruction import build_instruction
        base,quote=state["base_mint"],state["quote_mint"]
        if (mint_in,mint_out)==(base,quote):
            direction="sell"
        elif (mint_in,mint_out)==(quote,base):
            direction="buy_exact_quote_in"
        else:
            raise ValueError("PumpSwap pool mints disagree")
        if evidence.get("account_addresses_authenticated") is not True:
            raise ValueError("PumpSwap fee/account address authentication missing")
        addresses=dict(evidence.get("account_addresses") or {})
        if addresses.get("pool")!=pool or addresses.get("user")!=owner:
            raise ValueError("PumpSwap pool or signer address mismatch")
        if (addresses.get("user_base_token_account")!=(src if mint_in==base else dst)
                or addresses.get("user_quote_token_account")!=(src if mint_in==quote else dst)):
            raise ValueError("PumpSwap user token direction mismatch")
        if (addresses.get("base_mint"),addresses.get("quote_mint"))!=(base,quote):
            raise ValueError("PumpSwap authenticated mint mismatch")
        return build_instruction(direction,addresses,amount,floor)
    raise ValueError("unsupported execution venue")

