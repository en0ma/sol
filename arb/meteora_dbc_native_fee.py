"""Independent original DBC fee scheduler for standard SPL, no dynamic fee.

Uses original byte offsets from PoolConfig::PoolFeesConfig and Clock/PoolState.
Supports linear and exponential base scheduler only; rejects rate limiter,
Token-2022 transfer fees, variable fee, referral, activation before source.
"""
from arb.meteora_dbc_native_segment import Q64

DENOMINATOR=1_000_000_000
MAX_NUMERATOR=990_000_000
U64=(1<<64)-1


def fee_ceiling(amount,numerator):
    if type(amount) is not int or not 0<=amount<=U64:
        raise ValueError("DBC fee amount invalid")
    if type(numerator) is not int or not 0<=numerator<=MAX_NUMERATOR:
        raise ValueError("DBC fee numerator unsupported")
    return (amount*numerator+DENOMINATOR-1)//DENOMINATOR


def fee_numerator(config_raw, *, current_point,activation_point):
    if type(config_raw) is not bytes or len(config_raw)!=1048:
        raise ValueError("DBC original PoolConfig bytes required")
    if type(current_point) is not int or type(activation_point) is not int or (
            current_point<activation_point or activation_point<=0):
        raise ValueError("DBC authenticated fee activation point invalid")
    cliff=int.from_bytes(config_raw[104:112],"little")
    period_frequency=int.from_bytes(config_raw[112:120],"little")
    reduction=int.from_bytes(config_raw[120:128],"little")
    number_periods=int.from_bytes(config_raw[128:130],"little")
    mode=config_raw[130]
    dynamic=config_raw[136]
    if dynamic!=0 or mode not in (0,1):
        raise ValueError("DBC variable fee or rate limiter unsupported")
    if cliff>MAX_NUMERATOR or reduction>10_000:
        raise ValueError("DBC nonstandard fee scheduler")
    period=(min(number_periods,(current_point-activation_point)//period_frequency)
            if period_frequency else 0)
    if mode==0:
        numerator=cliff-period*reduction
        if numerator<0:raise ValueError("DBC negative linear fee")
        return numerator
    factor=Q64-(reduction*Q64)//10_000
    value=Q64
    # Implements bounded Q64 fixed-point exponent; numberOfPeriods <= u16.
    # Checked max to avoid pathological CI work and unsupported fee timelines.
    if period>64:raise ValueError("DBC long exponential scheduler unsupported")
    for _ in range(period):
        value=value*factor//Q64
    return min(MAX_NUMERATOR,cliff*value//Q64)


def split_fee(total):
    if type(total) is not int or not 0<=total<=U64:
        raise ValueError("DBC fee split amount invalid")
    protocol=total*20//100
    return {"protocol_fee":protocol,"trading_fee":total-protocol}


def price_with_fee(config_raw, *, direction, amount_in, price_curve_fn,
                   current_point,activation_point):
    """fee-aware quote, curve callback supplied by independent raw Q64 engine."""
    if type(amount_in) is not int or not 0<amount_in<=U64:
        raise ValueError("DBC zero/overflow fee quote input")
    if direction not in ("base_to_quote","quote_to_base"):
        raise ValueError("DBC unsupported trade direction")
    collection=config_raw[232]
    if collection not in (0,1):
        raise ValueError("DBC unsupported collect fee mode")
    numerator=fee_numerator(config_raw,current_point=current_point,
                            activation_point=activation_point)
    fees_on_input=direction=="quote_to_base" and collection==0
    excluded=amount_in-fee_ceiling(amount_in,numerator) if fees_on_input else amount_in
    if excluded<=0:raise ValueError("DBC fee exhausts input")
    gross=price_curve_fn(excluded)
    gross_out=gross["output_amount"]
    fees_on_output=not fees_on_input
    if fees_on_output:
        fee_amount=fee_ceiling(gross_out,numerator)
        output=gross_out-fee_amount
    else:
        fee_amount=amount_in-excluded
        output=gross_out
    if output<=0:raise ValueError("DBC quote output dust after fee")
    return {"actual_input_amount":excluded,
       "output_amount":output,"next_sqrt_price":gross["next_sqrt_price"],
       "fee_numerator":numerator,"fee_amount":fee_amount,
       **split_fee(fee_amount)}
