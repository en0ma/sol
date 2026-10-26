"""DAMM v2 venue-owned constant-product research quote.

Uses an explicitly supplied source-decoded effective fee and collection side.
Pool-specific range, scheduler and dynamic-fee evidence must be resolved by
the caller; this implementation cannot assert protocol exactness.
"""
DEN=1_000_000

def quote_exact_input(reserve_a,reserve_b,amount_in,*,input_is_a,
                      effective_fee_ppm,fee_token_side):
    if any(type(v)is not int for v in (reserve_a,reserve_b,amount_in,effective_fee_ppm)):
        raise ValueError("DAMM integer reserves and fee required")
    if min(reserve_a,reserve_b,amount_in)<=0 or not 0<amount_in<2**64:
        raise ValueError("invalid DAMM reserves or input")
    if not 0<=effective_fee_ppm<DEN or type(input_is_a)is not bool:
        raise ValueError("invalid DAMM fee or direction")
    if fee_token_side not in ("input","output"):
        raise ValueError("authenticated DAMM fee denomination required")
    reserve_in,reserve_out=(reserve_a,reserve_b) if input_is_a else (reserve_b,reserve_a)
    ceiling=lambda n,r:(n*r+DEN-1)//DEN
    input_fee=ceiling(amount_in,effective_fee_ppm) if fee_token_side=="input" else 0
    curve_input=amount_in-input_fee
    if curve_input<=0:raise ValueError("DAMM fee exhausts input")
    curve_out=reserve_out*curve_input//(reserve_in+curve_input)
    output_fee=ceiling(curve_out,effective_fee_ppm) if fee_token_side=="output" else 0
    received=curve_out-output_fee
    if not 0<received<reserve_out:raise ValueError("DAMM dust output")
    return {"amount_out":received,"fee_input_units":input_fee,
            "fee_output_units":output_fee,"fee_denomination":fee_token_side,
            "protocol_exact_verified":False,"requires_authenticated_dynamic_fee":True,
            "actionable":False,"live_execution_approved":False,"broadcast":False}
