"""Raydium CLMM conservative quote using authenticated fork fee and tick boundary.

Only within-tick indicative estimates; no swap broadcast or executable claim.
"""
from arb.raydium_clmm_quote_preflight import inspect_authenticated
from arb.raydium_clmm_fee_snapshot import read
from arb.raydium_clmm_within_tick_quote import quote_within_tick


def quote_live(rpc,pool,mint_in,amount_in):
    fee=read(rpc,pool)
    state=fee["state"]
    if mint_in not in (state["token_mint_0"],state["token_mint_1"]):
        raise ValueError("input mint not in CLMM pool")
    down=mint_in==state["token_mint_0"]
    proof=inspect_authenticated(rpc,pool,down)
    if (proof.get("boundary_observed") is not True or
            type(proof.get("boundary_sqrt_x64")) is not int or
            proof.get("fee_rate_ppm")!=fee["trade_fee_rate_ppm"] or
            proof.get("slot")!=fee["slot"]):
        raise ValueError("incomplete or non-atomic CLMM quote provenance")
    result=quote_within_tick(state,mint_in,amount_in,fee["trade_fee_rate_ppm"],
                             proof["boundary_sqrt_x64"])
    return {**result,"pool":pool,"slot":proof["slot"],
            "tick_boundary_authenticated":True,"fee_verified_onchain":True,
            "actionable":False,"executable_quote":False}
