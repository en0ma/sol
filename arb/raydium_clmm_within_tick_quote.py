"""Conservative exact-input Raydium CLMM within-current-tick quote.

Uses integer Q64.64 arithmetic, an explicitly authenticated fee rate, and a
verified next initialized tick boundary. Refuses any trade that crosses it.
A local model is still indicative: only signed Surfpool swaps verify execution.
"""
Q=1<<64
DENOM=1_000_000

def quote_within_tick(state,mint_in,amount_in,fee_rate_ppm,next_sqrt_x64):
    if type(amount_in) is not int or not 0<amount_in<1<<64:
        raise ValueError("invalid CLMM trade size")
    if type(fee_rate_ppm) is not int or not 0<=fee_rate_ppm<DENOM:
        raise ValueError("missing authenticated CLMM fee")
    m0,m1=state["token_mint_0"],state["token_mint_1"]
    if mint_in not in (m0,m1) or m0==m1:
        raise ValueError("CLMM input mint mismatch")
    zero_for_one=mint_in==m0
    p,l=state.get("sqrt_price_x64"),state.get("liquidity")
    if (type(p) is not int or type(l) is not int or
            not 0<p<1<<128 or not 0<l<1<<128 or
            type(next_sqrt_x64) is not int or
            not (0<next_sqrt_x64<p if zero_for_one else p<next_sqrt_x64<1<<128)):
        raise ValueError("invalid authenticated tick boundary or pool state")
    effective=amount_in-(amount_in*fee_rate_ppm+DENOM-1)//DENOM
    if effective<=0:raise ValueError("trade entirely consumed by fees")
    if zero_for_one:
        new_p=(l*Q*p+l*Q+effective*p-1)//(l*Q+effective*p)
        if new_p<=next_sqrt_x64 or new_p>=p:
            raise ValueError("trade crosses initialized tick or is dust")
        amount_out=l*(p-new_p)//Q
    else:
        new_p=p+effective*Q//l
        if new_p>=next_sqrt_x64 or new_p<=p:
            raise ValueError("trade crosses initialized tick or is dust")
        amount_out=l*Q*(new_p-p)//(new_p*p)
    if not 0<amount_out<1<<64:
        raise ValueError("zero or overflowing CLMM output")
    return {"status":"INDICATIVE_WITHIN_TICK_ONLY","mint_in":mint_in,
        "mint_out":m1 if zero_for_one else m0,"amount_in":amount_in,
        "estimated_output_base_units":amount_out,"next_sqrt_price_x64":new_p,
        "fee_rate_ppm":fee_rate_ppm,"crossed_ticks":0,
        "actionable":False,"executable_quote":False,"simulation_verified":False}
