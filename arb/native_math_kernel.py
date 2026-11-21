"""Independently check exact integer CPMM pricing for explicit fee-model inputs.

This shared mathematical kernel does not pretend CLMM ticks, DLMM bins, DAMM
dynamic fees, PumpSwap virtual reserves or AMM v4 OpenBook depth are CPMM.
Those venue-specific inputs must be source-verified and independently audited.
"""
U64=2**64
DENOM=1_000_000

def exact_constant_product_quote(*,reserve_in,reserve_out,amount_in,fee_rate,
                                  fee_denominator=DENOM):
    values=(reserve_in,reserve_out,amount_in,fee_rate,fee_denominator)
    if (any(type(x)is not int for x in values)
        or not 0<reserve_in<U64 or not 0<reserve_out<U64
        or not 0<amount_in<U64 or not 0<fee_denominator<=10**12
        or not 0<=fee_rate<fee_denominator):
        raise ValueError("invalid authenticated reserves, input or fee model")
    fee=(amount_in*fee_rate+fee_denominator-1)//fee_denominator
    net=amount_in-fee
    if net<=0:raise ValueError("fee consumes entire input")
    output=net*reserve_out//(reserve_in+net)
    if not 0<output<reserve_out:
        raise ValueError("no positive output or insufficient reserves")
    return {"amount_in_base_units":amount_in,
            "amount_out_base_units":output,
            "swap_fee_input_base_units":fee,
            "exact_integer_math":True,
            "source_state_independently_authenticated_here":False,
            "native_signed_parity_verified":False,
            "net_profitability_verified":False,
            "actionable":False,"live_execution_approved":False,"broadcast":False}
