"""Independent DBC integer curve arithmetic (zero-fee per-segment primitive).

Upstream DBC prices and liquidity use Q128 fixed point, not Q64.
These primitives are NOT full pool fee/scheduler/migration logic and must
not be called signed-price parity without the original SDK comparison.
"""
U64=(1<<64)-1
U128=(1<<128)-1
U256=(1<<256)-1
Q128=1<<128


def bounded(value,high,label):
    if type(value) is not int or not 0<=value<=high:
        raise ValueError("DBC "+label+" out of unsigned bounds")
    return value


def divide(n,d,up=False):
    if d<=0:raise ValueError("DBC zero denominator")
    return (n+d-1)//d if up else n//d


def next_sqrt_from_exact_input(sqrt_price,liquidity,amount,base_for_quote):
    bounded(sqrt_price,U128,"sqrt_price")
    bounded(liquidity,U256,"liquidity")
    bounded(amount,U64,"amount")
    if sqrt_price==0 or liquidity==0:
        raise ValueError("DBC zero price/liquidity")
    if base_for_quote:
        value=divide(liquidity*sqrt_price,
                     liquidity+amount*sqrt_price,True)
    else:
        value=sqrt_price+divide(amount*Q128,liquidity)
    return bounded(value,U128,"next_sqrt_price")


def delta_base(lower,upper,liquidity,up=False):
    bounded(lower,U128,"lower");bounded(upper,U128,"upper")
    bounded(liquidity,U128,"liquidity")
    if not 0<lower<=upper:
        raise ValueError("DBC invalid sqrt price bounds")
    return divide(liquidity*(upper-lower),lower*upper,up)


def delta_quote(lower,upper,liquidity,up=False):
    bounded(lower,U128,"lower");bounded(upper,U128,"upper")
    bounded(liquidity,U128,"liquidity")
    if lower>upper:
        raise ValueError("DBC inverted sqrt price bounds")
    return divide(liquidity*(upper-lower),Q128*Q128,up)


def quote_one_segment(*,sqrt_price,liquidity,input_amount,base_for_quote,
                      target_price):
    """Exact input within ONE segment, zero fee, no partial fills.

    No claim of DBC pool quote/SDK parity; the full curve and fee modes
    must be independently handled before accepting real swaps.
    """
    bounded(input_amount,U64,"input")
    bounded(target_price,U128,"target")
    if input_amount==0:raise ValueError("DBC zero input")
    nxt=next_sqrt_from_exact_input(sqrt_price,liquidity,input_amount,
                                   base_for_quote)
    if (base_for_quote and nxt<target_price) or (
            not base_for_quote and nxt>target_price):
        raise ValueError("DBC tick/curve segment crossing unsupported")
    out=(delta_quote(nxt,sqrt_price,liquidity) if base_for_quote else
         delta_base(sqrt_price,nxt,liquidity))
    bounded(out,U64,"output")
    if out==0:raise ValueError("DBC dust quote")
    return {"output_amount":out,"next_sqrt_price":nxt,
            "fee_amount":0,"single_segment_only":True,
            "full_pool_sdk_parity":False,"signed_verified":False}
