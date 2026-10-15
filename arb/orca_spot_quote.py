"""Conservative single-tick indicative Orca Whirlpool quotes for discovery.

Uses verified Whirlpool sqrt price, liquidity, and fee; deliberately rejects
tick crossings rather than inventing a multi-tick quote. For candidate ranking
only, never authorizes execution or profitability claims.
"""
from arb.orca_whirlpool import fetch_pool
from arb.whirlpool_preflight import verify_oracle
Q=1<<64
FEE_DENOM=1_000_000

def quote_single_tick(state,mint_in,amount_in):
    if type(amount_in)is not int or not 0<amount_in<1<<64:
        raise ValueError("invalid amount")
    a,b=state["token_mint_a"],state["token_mint_b"]
    if mint_in not in (a,b):raise ValueError("mint not in pool")
    L=int(state["liquidity"]);p=int(state["sqrt_price_x64"])
    fee=state["fee_rate_hundredths_bps"]
    if L<=0 or p<=0 or type(fee)is not int or not 0<=fee<FEE_DENOM:
        raise ValueError("invalid liquidity, price or fee")
    effective=amount_in*(FEE_DENOM-fee)//FEE_DENOM
    if effective<=0:raise ValueError("amount eaten by fees")
    if mint_in==a:
        next_p=(L*Q*p+(L*Q+effective*p)-1)//(L*Q+effective*p)
        output=L*(p-next_p)//Q
    else:
        next_p=p+effective*Q//L
        output=L*Q*(next_p-p)//(p*next_p)
    if next_p<=0 or output<=0:raise ValueError("dust quote")
    return {"mint_in":mint_in,"mint_out":b if mint_in==a else a,
            "amount_in":amount_in,"estimated_output_base_units":output,
            "fee_rate_ppm":fee,"post_sqrt_price_x64":str(next_p),
            "tick_boundary_verified":False,"status":"INDICATIVE_SPOT_ONLY",
            "actionable":False,"executable_quote":False}

def quote_pool_state(state,mint_in,amount_in):
    return quote_single_tick(state,mint_in,amount_in)
