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
