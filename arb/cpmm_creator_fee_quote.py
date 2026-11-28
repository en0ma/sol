"""Venue-owned source-informed CPMM creator-fee research calculations.

All amounts are integer SPL base units. This is an indicative price study,
not a transaction proposal or signed-output verification.
"""
DEN=1000000

def calculate(reserve_in,reserve_out,amount_in,trade_ppm,creator_ppm,mode,input_index,enabled=True):
    if any(type(x) is not int for x in (reserve_in,reserve_out,amount_in,trade_ppm,creator_ppm,mode,input_index)):
        raise ValueError("integer inputs required")
    if min(reserve_in,reserve_out,amount_in)<=0 or not 0<amount_in<2**64:
        raise ValueError("invalid vault amounts or input")
    if not (0<=trade_ppm<DEN and 0<=creator_ppm<DEN and mode in (0,1,2)
            and input_index in (0,1) and type(enabled) is bool):
        raise ValueError("invalid fee config")
    side_input=(mode==0 or mode==input_index+1)
    rate=creator_ppm if enabled else 0
    ceiling=lambda amount,ppm:(amount*ppm+DEN-1)//DEN
    # Deployed cp-swap CurveCalculator::swap_base_input charges one
    # ceiling-rounded combined input fee and then allocates the creator
    # portion with floor(total_fee * creator_rate / combined_rate).
    # Independently ceiling-rounding the two rates overcharges dust swaps.
    if side_input:
        combined_rate=trade_ppm+rate
        if combined_rate==0:
            raise ValueError("zero combined fee unsupported by native creator split")
        total_fee=ceiling(amount_in,combined_rate)
        creator_input=total_fee*rate//combined_rate
        trading=total_fee-creator_input
    else:
        trading=ceiling(amount_in,trade_ppm)
        creator_input=0
    remaining=amount_in-trading-creator_input
    if remaining<=0:raise ValueError("fee exceeds swap input")
    curve=reserve_out*remaining//(reserve_in+remaining)
    creator_output=ceiling(curve,rate) if not side_input else 0
    received=curve-creator_output
    if not 0<received<reserve_out:raise ValueError("no swap output")
    return {"estimated_output_base_units":received,
            "trade_fee_input_base_units":trading,
            "creator_fee_base_units":creator_input+creator_output,
            "creator_fee_mint_side":"input" if side_input else "output",
            "protocol_exact_verified":False,"simulation_only":True}

def effective_reserves(pool_state,vault_amounts):
    """PoolState.vault_amount_without_fee: exclude accrued fee liabilities."""
    if not isinstance(vault_amounts,list) or len(vault_amounts)!=2:
        raise ValueError("two source vault amounts required")
    out=[]
    for i in (0,1):
        vault=vault_amounts[i]
        keys=[f"protocol_fees_token_{i}",f"fund_fees_token_{i}",
              f"creator_fees_token_{i}"]
        fees=[pool_state.get(k) for k in keys]
        if type(vault)is not int or vault<=0 or any(type(n)is not int or n<0 for n in fees):
            raise ValueError("accrued CPMM fee liabilities not authenticated")
        net=vault-sum(fees)
        if net<=0:raise ValueError("CPMM fees exhaust vault reserves")
        out.append(net)
    return out
