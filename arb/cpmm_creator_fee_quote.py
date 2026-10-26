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
    trading=ceiling(amount,trade_ppm)
    creator_input=ceiling(amount_in,rate) if side_input else 0
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
