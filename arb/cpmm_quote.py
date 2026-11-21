"""Integer-only CPMM indicative quote primitive for route search.

Fees must be supplied from a VERIFIED on-chain AMM configuration.
Pool decoder and vault reserves alone do not prove the actual swap fee.
No external pricing or unsupported default fee is invented.
"""
FEE_DENOMINATOR=1_000_000

def quote_exact_input(reserve_in,reserve_out,amount_in,trade_fee_rate):
    """Constant-product amount out, rounding down, not execution guarantee."""
    vals=(reserve_in,reserve_out,amount_in,trade_fee_rate)
    if any(type(v) is not int for v in vals):
        raise TypeError("CPMM quote uses only integer base units")
    if reserve_in<=0 or reserve_out<=0 or not 0<amount_in<2**64:
        raise ValueError("invalid reserves or trade size")
    if not 0<=trade_fee_rate<FEE_DENOMINATOR:
        raise ValueError("fee rate must be verified ppm")
    effective=amount_in*(FEE_DENOMINATOR-trade_fee_rate)
    denominator=reserve_in*FEE_DENOMINATOR+effective
    output=(reserve_out*effective)//denominator
    if not 0<output<reserve_out:
        raise ValueError("dust/empty CPMM output")
    fee=amount_in*trade_fee_rate//FEE_DENOMINATOR
    return {"amount_in":amount_in,"estimated_output_base_units":output,
            "trade_fee_rate_ppm":trade_fee_rate,"estimated_fee_base_units":fee,
            "exact_swap_simulated":False,"executable_quote":False}

def quote_pool(pool,mint_in,amount_in,verified_trade_fee_rate=None):
    if pool.get("venue")!="raydium_cpmm" or not pool.get("verified"):
        raise ValueError("not a verified CPMM pool")
    if verified_trade_fee_rate is None:
        raise ValueError("verified on-chain fee configuration required")
    mints=pool.get("mints");reserves=pool.get("vault_base_units")
    if not isinstance(mints,list) or len(mints)!=2 or len(set(mints))!=2:
        raise ValueError("invalid mint pair")
    if not isinstance(reserves,list) or len(reserves)!=2:
        raise ValueError("missing validated vault reserves")
    if mint_in not in mints:raise ValueError("input mint not in pool")
    side=mints.index(mint_in)
    return {**quote_exact_input(reserves[side],reserves[1-side],
                                amount_in,verified_trade_fee_rate),
            "pool":pool["address"],"mint_in":mint_in,
            "mint_out":mints[1-side],"indicative_only":True}

def quote_fee_rounding_interval(reserve_in,reserve_out,amount_in,trade_fee_rate):
    """Account-derived CPMM output interval for floor/ceiling fee rounding.

    Uses exact integer reserve invariant. An observed signed output outside
    this interval cannot be explained by input fee rounding alone.
    """
    vals=(reserve_in,reserve_out,amount_in,trade_fee_rate)
    if any(type(x)is not int for x in vals) or min(reserve_in,reserve_out,amount_in)<=0:
        raise ValueError("positive integer CPMM inputs required")
    if not 0<=trade_fee_rate<FEE_DENOMINATOR or amount_in>=2**64:
        raise ValueError("invalid CPMM fee or input")
    fee_floor=amount_in*trade_fee_rate//FEE_DENOMINATOR
    fee_ceil=(amount_in*trade_fee_rate+FEE_DENOMINATOR-1)//FEE_DENOMINATOR
    def out(fee):
        effective=amount_in-fee
        return reserve_out*effective//(reserve_in+effective)
    return {"fee_floor_input_units":fee_floor,"fee_ceiling_input_units":fee_ceil,
            "output_interval_base_units":[out(fee_ceil),out(fee_floor)],
            "protocol_exact_verified":False}

def quote_native_fee_candidates(reserve_in,reserve_out,amount_in,trade_fee_rate):
    """Compare integer fee-debit paths with fractional-invariant CPMM quote.

    These are explicit alternative rounding rules, not claims of matching
    the currently deployed CPMM implementation.
    """
    interval=quote_fee_rounding_interval(reserve_in,reserve_out,amount_in,trade_fee_rate)
    ratio=quote_exact_input(reserve_in,reserve_out,amount_in,trade_fee_rate)
    lo,hi=interval["output_interval_base_units"]
    return {"fractional_invariant_output_base_units":ratio["estimated_output_base_units"],
            "floor_fee_then_swap_output_base_units":hi,
            "ceil_fee_then_swap_output_base_units":lo,
            "fee_floor_input_units":interval["fee_floor_input_units"],
            "fee_ceil_input_units":interval["fee_ceiling_input_units"],
            "source_fee_rate_ppm":trade_fee_rate,
            "protocol_exact_verified":False}

def quote_source_exact_input(pool_state,config,*,reserve_0,reserve_1,
                             amount_in,input_is_token_0,observed_unix,
                             transfer_fee_in=0,transfer_fee_out=0):
    """Raydium cp-swap CurveCalculator::swap_base_input semantics.

    Source: raydium-io/raydium-cp-swap programs/cp-swap/src/curve/calculator.rs
    and states/pool.rs. A quote is NOT signed-verified until Surfpool parity.
    Token-2022 transfer fees must be independently authenticated; for classic
    SPL tokens they are zero. No default fee rates or invented reserves.
    """
    if not isinstance(pool_state,dict) or not isinstance(config,dict):
        raise ValueError("authenticated CPMM pool/config state required")
    if config.get("fee_verified_onchain") is not True:
        raise ValueError("on-chain CPMM config authentication required")
    if (any(type(v)is not int for v in (reserve_0,reserve_1,amount_in,
            observed_unix,transfer_fee_in,transfer_fee_out)) or
            type(input_is_token_0)is not bool or
            not 0<amount_in<2**64 or min(reserve_0,reserve_1)<=0 or
            min(transfer_fee_in,transfer_fee_out)<0):
        raise ValueError("invalid CPMM signed source pricing inputs")
    if (pool_state.get("swap_enabled") is not True or
            type(pool_state.get("open_time"))is not int or
            observed_unix<pool_state["open_time"]):
        raise ValueError("CPMM pool swaps disabled or not yet opened")
    from arb.token_vaults import TOKEN_PROGRAM
    if (pool_state.get("token_0_program")!=TOKEN_PROGRAM or
            pool_state.get("token_1_program")!=TOKEN_PROGRAM or
            transfer_fee_in or transfer_fee_out):
        raise ValueError("unsupported CPMM token-2022 transfer fee; classic SPL only")
    accrued=[]
    for i in (0,1):
        vals=[pool_state.get(f"{kind}_fees_token_{i}") for kind in
              ("protocol","fund","creator")]
        if any(type(v)is not int or v<0 for v in vals):
            raise ValueError("CPMM source accrued-fee state absent")
        accrued.append(sum(vals))
    x,y=reserve_0-accrued[0],reserve_1-accrued[1]
    if min(x,y)<=0:
        raise ValueError("CPMM fee-adjusted reserve empty")
    reserve_in,reserve_out=(x,y) if input_is_token_0 else (y,x)
    mode=pool_state.get("creator_fee_on")
    if type(mode)is not int or mode not in (0,1,2):
        raise ValueError("CPMM creator fee mode unsupported")
    creator_on_input=mode==0 or (mode==1 and input_is_token_0) or (mode==2 and not input_is_token_0)
    def rate(k):
        v=config.get(k)
        if type(v)is not int or not 0<=v<FEE_DENOMINATOR:
            raise ValueError("CPMM authenticated fee rate missing: "+k)
        return v
    trade=rate("trade_fee_rate_ppm")
    creator=rate("creator_fee_rate_ppm") if pool_state.get("enable_creator_fee") is True else 0
    protocol=rate("protocol_fee_rate_ppm")
    fund=rate("fund_fee_rate_ppm")
    if trade+creator>=FEE_DENOMINATOR or protocol+fund>FEE_DENOMINATOR:
        raise ValueError("CPMM on-chain fee rate overflow")
    ceil=lambda a,n:(a*n+FEE_DENOMINATOR-1)//FEE_DENOMINATOR
    # Raydium aggregates creator+trade input fees BEFORE rounding and splits
    # creator share using integer floor; never round separate fees here.
    if creator_on_input:
        combined_fee=ceil(amount_in,trade+creator)
        creator_fee=(combined_fee*creator//(trade+creator)) if trade+creator else 0
        trade_fee=combined_fee-creator_fee
        effective=amount_in-combined_fee
    else:
        trade_fee=ceil(amount_in,trade)
        effective=amount_in-trade_fee
        creator_fee=0
    if effective<=0:raise ValueError("CPMM fees exhaust input")
    curve_output=reserve_out*effective//(reserve_in+effective)
    if not creator_on_input:
        creator_fee=ceil(curve_output,creator)
    output=curve_output-(creator_fee if not creator_on_input else 0)
    if not 0<output<reserve_out or output>=2**64:
        raise ValueError("CPMM output dust or overflow")
    protocol_fee=trade_fee*protocol//FEE_DENOMINATOR
    fund_fee=trade_fee*fund//FEE_DENOMINATOR
    return {"amount_out":output,"estimated_output_base_units":output,
            "trade_fee":trade_fee,"creator_fee":creator_fee,
            "protocol_fee":protocol_fee,"fund_fee":fund_fee,
            "creator_fee_on_input":creator_on_input,
            "effective_reserves":[reserve_in,reserve_out],
            "native_pricing_engine":"RAYDIUM_CP_SWAP_CURVE_CALCULATOR_PORT",
            "source_authenticated":True,
            "protocol_exact_verified":False,
            "signed_execution_parity_verified":False,
            "actionable":False,"live_execution_approved":False,"broadcast":False}
