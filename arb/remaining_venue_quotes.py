"""Strict indicative models. Require independently authenticated full-fee inputs.
DLMM limited to one bin; DAMM v2 to one fixed-liquidity segment;
AMM v4 to reconciled OpenBook/PnL-adjusted reserves. Never execution proof.
"""
from arb.cpmm_quote import quote_exact_input
from arb.raydium_clmm_within_tick_quote import quote_within_tick
Q=1<<64
def quote(s,leg,n):
    v=s["venue"];a,b=s["mints"];src=leg["input_mint"]
    if (src,leg["output_mint"]) not in ((a,b),(b,a)):
        raise ValueError("invalid quote direction")
    f=s.get("trade_fee_ppm")
    if s.get("trade_fee_authenticated") is not True or type(f)is not int or not 0<=f<1000000:
        raise ValueError("authenticated effective trade fee missing")
    fee=(n*f+999999)//1000000
    if v=="raydium_amm_v4":
        if (s.get("base_mint"),s.get("quote_mint"))!=(a,b) or s.get("market_accounts_authenticated") is not True or s.get("effective_reserves_authenticated") is not True:
            raise ValueError("AMM v4 market and adjusted reserves not authenticated")
        r=s.get("effective_reserves_base_units")
        if not isinstance(r,list) or len(r)!=2 or any(type(x)is not int or x<=0 for x in r):
            raise ValueError("AMM v4 net reserve accounting missing")
        i=0 if src==a else 1
        x=quote_exact_input(r[i],r[1-i],n,f)
        return x["estimated_output_base_units"],fee,r[i],"AMM_V4_ADJUSTED_CPMM_INDICATIVE"
    if v not in ("meteora_dlmm","meteora_damm_v2"):
        raise ValueError("unsupported quote venue")
    limits=s.get("max_within_segment_input_by_mint")
    depth=limits.get(src) if isinstance(limits,dict) else None
    if type(depth)is not int or depth<=0 or n>depth:
        raise ValueError("unauthenticated or crossed price segment")
    if v=="meteora_dlmm":
        if (s.get("token_x_mint"),s.get("token_y_mint"))!=(a,b) or s.get("active_bin_authenticated") is not True or s.get("bin_liquidity_authenticated") is not True:
            raise ValueError("DLMM bin not authenticated")
        p=s.get("active_bin_price_q64")
        reserves=(s.get("active_bin_x_reserve"),s.get("active_bin_y_reserve"))
        if type(p)is not int or p<=0 or any(type(x)is not int or x<=0 for x in reserves):
            raise ValueError("DLMM bin price/liquidity missing")
        effective=n-fee
        out=effective*p//Q if src==a else effective*Q//p
        if out<=0 or out>reserves[1 if src==a else 0]:
            raise ValueError("DLMM output exceeds authenticated active bin")
        return out,fee,depth,"DLMM_SINGLE_BIN_INDICATIVE"
    if (s.get("token_a_mint"),s.get("token_b_mint"))!=(a,b) or s.get("dynamic_fee_authenticated") is not True or s.get("price_segment_authenticated") is not True:
        raise ValueError("DAMM v2 segment and dynamic fee not authenticated")
    bounds=s.get("next_segment_sqrt_by_input_mint")
    boundary=bounds.get(src) if isinstance(bounds,dict) else None
    if type(boundary)is not int:
        raise ValueError("DAMM v2 authenticated segment boundary missing")
    raw=quote_within_tick({"token_mint_0":a,"token_mint_1":b,
        "sqrt_price_x64":s.get("sqrt_price_x64"),"liquidity":s.get("liquidity")},
        src,n,f,boundary)
    return raw["estimated_output_base_units"],fee,depth,"DAMM_V2_SINGLE_SEGMENT_INDICATIVE"
