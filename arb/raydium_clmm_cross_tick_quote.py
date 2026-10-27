"""Integer exact-input traversal across authenticated Raydium CLMM initialized ticks.

This is a venue-owned Q64.64 swap model, not a quote supplied by a routing
heuristic. Every crossing consumes a fully authenticated TickArrayState tick.
No virtual ticks, guessed tick liquidity, extrapolated arrays, or floating point.
Source prices/fee and tick-array PDA binding are validated by the caller.
"""
Q=1<<64
DEN=1_000_000
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}

def ceil_div(x,y):
    if type(x)is not int or type(y)is not int or x<0 or y<=0:
        raise ValueError("invalid CLMM integer ceiling operands")
    return (x+y-1)//y

def delta_input(liquidity,at,limit,zero_for_one):
    if zero_for_one:
        return ceil_div(liquidity*Q*(at-limit),at*limit)
    return ceil_div(liquidity*(limit-at),Q)

def delta_output(liquidity,at,limit,zero_for_one):
    if zero_for_one:
        return liquidity*(at-limit)//Q
    return liquidity*Q*(limit-at)//(at*limit)

def advance_sqrt(liquidity,at,net,zero_for_one):
    if zero_for_one:
        return ceil_div(liquidity*Q*at,liquidity*Q+net*at)
    return at+net*Q//liquidity

def quote_across_initialized_ticks(state,mint_in,amount_in,fee_rate_ppm,ticks,
                                  *,max_crossings=32):
    """Simulate crossing source-initialized ticks, respecting per-tick liquidity net.

    Fee rounding is per swap step. A limit-cross requires enough gross input to
    cover its net input plus the fee (ceil), with any unspent amount conserved.
    If the active liquidity becomes zero or a next tick is missing, reject.
    """
    if type(amount_in)is not int or not 0<amount_in<2**64:
        raise ValueError("CLMM exact input must fit u64")
    if type(fee_rate_ppm)is not int or not 0<=fee_rate_ppm<DEN:
        raise ValueError("CLMM authenticated fee ppm required")
    if type(max_crossings)is not int or not 0<=max_crossings<=256:
        raise ValueError("CLMM crossing limit invalid")
    m0,m1=state["token_mint_0"],state["token_mint_1"]
    if mint_in not in (m0,m1) or m0==m1:
        raise ValueError("CLMM source mint direction mismatch")
    zero=mint_in==m0
    price=state.get("sqrt_price_x64")
    liq=state.get("liquidity")
    tick=state.get("tick_current")
    if (any(type(x)is not int for x in (price,liq,tick))
            or not 0<price<1<<128 or not 0<liq<1<<128):
        raise ValueError("CLMM current price or liquidity absent")
    if not isinstance(ticks,list) or not 1<=len(ticks)<=300:
        raise ValueError("source initialized tick inventory empty or unbounded")
    # Nonadjacent on-chain arrays can conceal intervening initialized
    # liquidity. Require explicit positional range coverage when supplied.
    # The caller performs same-slot PDA and program ownership authentication.
    starts=state.get("authenticated_tick_array_starts")
    if starts is not None:
        spacing=state.get("tick_spacing")
        if (not isinstance(starts,list) or not starts or
                any(type(v)is not int for v in starts) or len(set(starts))!=len(starts)
                or type(spacing)is not int or spacing<=0):
            raise ValueError("CLMM authenticated tick array range malformed")
        span=60*spacing
        anchor=tick//span*span
        if anchor not in starts:
            raise ValueError("CLMM active tick array missing from authenticated range")
        for start in starts:
            if start%span:
                raise ValueError("CLMM tick array range not aligned")
    by_index={}
    for row in ticks:
        if not isinstance(row,dict):
            raise ValueError("malformed CLMM source initialized tick")
        i,net,gross=(row.get(k) for k in ("tick_index","liquidity_net","liquidity_gross"))
        if (any(type(x)is not int for x in (i,net,gross)) or
                i in by_index or not -443636<=i<=443636 or
                gross<=0 or abs(net)>gross):
            raise ValueError("source CLMM tick index, liquidity or uniqueness invalid")
        by_index[i]=row
    from arb.orca_tick_math import sqrt_price_from_tick_index
    remaining=amount_in
    fee_total=out=0
    current_tick=tick
    crossed=[]
    steps=[]
    while remaining:
        candidates=([i for i in by_index if i<=current_tick] if zero
                    else [i for i in by_index if i>current_tick])
        if not candidates:
            raise ValueError("CLMM next initialized tick missing from source account inventory")
        target_index=max(candidates) if zero else min(candidates)
        if starts is not None:
            target_start=target_index//span*span
            first=min(anchor,target_start)
            last=max(anchor,target_start)
            for array_start in range(first,last+span,span):
                if array_start not in starts:
                    raise ValueError("CLMM source tick array range has an unobserved gap")
        target=sqrt_price_from_tick_index(target_index)
        if zero and target>price:
            raise ValueError("CLMM downwards initialized tick above active price")
        if not zero and target<price:
            raise ValueError("CLMM upwards initialized tick below active price")
        # A source tick at the current exact price must still apply its signed
        # liquidity delta; the zero-delta crossing does not spend swap input.
        needed=delta_input(liq,price,target,zero)
        gross_to_limit=ceil_div(needed*DEN,DEN-fee_rate_ppm)
        if remaining>=gross_to_limit:
            spent=gross_to_limit
            next_price=target
            reached=True
            net_in=needed
        else:
            spent=remaining
            fee=ceil_div(spent*fee_rate_ppm,DEN)
            net_in=spent-fee
            if net_in<=0:
                raise ValueError("CLMM input entirely exhausted by swap fees")
            next_price=advance_sqrt(liq,price,net_in,zero)
            if next_price==price or (next_price<=target if zero else next_price>=target):
                raise ValueError("CLMM zero price movement or unverified tick crossing")
            reached=False
        if spent<0 or spent>remaining:
            raise ValueError("CLMM swap input accounting underflow")
        fee=spent-net_in
        got=delta_output(liq,price,next_price,zero)
        if got<0:
            raise ValueError("CLMM output calculation negative")
        remaining-=spent
        fee_total+=fee
        out+=got
        steps.append({"from_sqrt_x64":price,"to_sqrt_x64":next_price,
                      "source_next_tick":target_index,"gross_input_base_units":spent,
                      "net_input_base_units":net_in,"fee_input_base_units":fee,
                      "output_base_units":got,"liquidity_before":liq,
                      "initialized_tick_crossed":reached})
        price=next_price
        if not reached:
            break
        if len(crossed)>=max_crossings:
            if remaining:raise ValueError("CLMM authenticated crossing budget exhausted")
            break
        change=by_index[target_index]["liquidity_net"]
        after=liq-change if zero else liq+change
        if not 0<after<1<<128:
            if remaining:raise ValueError("CLMM crossing has zero or invalid next liquidity")
        liq=after
        crossed.append({"tick_index":target_index,
                        "source_liquidity_net":change,
                        "liquidity_after_crossing":liq})
        current_tick=target_index-1 if zero else target_index
        if len(steps)>max_crossings+1:
            raise ValueError("CLMM crossing iteration bound")
    if remaining or not 0<out<2**64:
        raise ValueError("CLMM source arrays cannot fully fill positive exact input")
    return {"status":"SOURCE_AUTHENTICATED_CLMM_CROSS_TICK_MODEL",
            "amount_in":amount_in,"amount_out":out,
            "input_mint":mint_in,"output_mint":m1 if zero else m0,
            "fee_input_base_units":fee_total,"final_sqrt_price_x64":price,
            "crossed_ticks":len(crossed),"crossed_source_liquidity":crossed,
            "steps":steps,"exact_input_filled":True,
            "tick_array_liquidity_source_verified":True,
            "protocol_exact_verified":False,"signed_simulation_verified":False,**SAFE}
