"""Independent original Meteora DBC multi-segment Q64 exact-input curve walk.

Direct integer implementation of original curve point traversal, with
source-config bounded 20 points, no SDK mathematics called at runtime.
Fees, scheduling, migration constraints and transfer tokens are separate.
"""
from arb.meteora_dbc_native_segment import (
    U64,U128,delta_base,delta_quote,next_sqrt_from_exact_input,
)


def walk(*,sqrt_price,amount_in,base_for_quote,curve,sqrt_start_price,
         migration_sqrt_price=None):
    if (type(amount_in) is not int or not 0<amount_in<=U64
            or type(sqrt_price) is not int or not 0<sqrt_price<=U128
            or type(sqrt_start_price) is not int or not 0<sqrt_start_price<sqrt_price
            or type(base_for_quote) is not bool
            or not isinstance(curve,list) or not 1<=len(curve)<=20):
        raise ValueError("DBC original curve-walk inputs invalid")
    if any(not isinstance(x,(tuple,list)) or len(x)!=2 or
           type(x[0]) is not int or type(x[1]) is not int or
           not 0<x[0]<=U128 or x[1]<=0 for x in curve):
        raise ValueError("DBC curve points structurally unsupported")
    if any(curve[i][0]>=curve[i+1][0] for i in range(len(curve)-1)):
        raise ValueError("DBC original curve points not increasing")
    if sqrt_price>=curve[-1][0]:
        raise ValueError("DBC source sqrt price above final curve point")
    amount_left=amount_in
    current=sqrt_price
    received=0
    if base_for_quote:
        # Walk downward across the original curve from highest occupied point.
        for i in range(len(curve)-2,-1,-1):
            lower=curve[i][0]
            liquidity=curve[i+1][1]
            if lower>=current:
                continue
            max_input=delta_base(lower,current,liquidity,up=True)
            if amount_left<max_input:
                nxt=next_sqrt_from_exact_input(current,liquidity,
                                               amount_left,True)
                received+=delta_quote(nxt,current,liquidity)
                current=nxt;amount_left=0
                break
            received+=delta_quote(lower,current,liquidity)
            current=lower;amount_left-=max_input
        if amount_left:
            liquidity=curve[0][1]
            nxt=next_sqrt_from_exact_input(current,liquidity,
                                           amount_left,True)
            if nxt<sqrt_start_price:
                nxt=sqrt_start_price
                amount_left-=delta_base(nxt,current,liquidity,up=True)
            else:
                amount_left=0
            received+=delta_quote(nxt,current,liquidity)
            current=nxt
    else:
        if type(migration_sqrt_price) is not int or not 0<migration_sqrt_price<=U128:
            raise ValueError("DBC authenticated migration sqrt price required")
        for point,liquidity in curve:
            upper=min(point,migration_sqrt_price)
            if upper<=current:
                continue
            max_input=delta_quote(current,upper,liquidity,up=True)
            if amount_left<max_input:
                nxt=next_sqrt_from_exact_input(current,liquidity,
                                               amount_left,False)
                received+=delta_base(current,nxt,liquidity)
                current=nxt;amount_left=0
                break
            received+=delta_base(current,upper,liquidity)
            current=upper;amount_left-=max_input
            if current==migration_sqrt_price:
                break
    if amount_left or not 0<received<=U64:
        raise ValueError("DBC unsupported partial-fill or dust curve output")
    return {"output_amount":received,"next_sqrt_price":current,
            "amount_left":0,"multi_segment_curve_math":True,
            "native_full_fee_verified":False,"signed_verified":False}
