"""Fail-closed protocol-specific quote-model contract for seven venues.

Each venue requires its own fully authenticated native state and pricing
algorithm. Unknown fee tiers, ticks/bins or unverified price sources cannot be
replaced with constant-product approximations. Explicitly blocks unsupported
models instead of manufacturing positive arbitrage.
"""
VENUE_MODELS={
 "raydium_cpmm":"CPMM_INTEGER_FEES_AND_VAULT_RESERVES",
 "raydium_amm_v4":"OPENBOOK_PLUS_AMM_RESERVES_AND_PNL",
 "orca":"WHIRLPOOL_TICK_ARRAY_SWAP_STEP",
 "raydium_clmm":"CONCENTRATED_LIQUIDITY_TICK_ARRAY_SWAP_STEP",
 "meteora_dlmm":"BIN_ARRAY_DYNAMIC_FEE",
 "meteora_damm_v2":"DAMM_V2_DYNAMIC_FEE_AND_SQRT_PRICE",
 "pumpswap":"PUMPSWAP_FEE_TIER_VIRTUAL_RESERVE"}
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
def model_requirements(venue):
    if venue not in VENUE_MODELS:
        raise ValueError("unsupported venue")
    return {"venue":venue,"native_pricing_model":VENUE_MODELS[venue],
            "independent_native_pricing_implemented":venue=="raydium_cpmm",
            "source_state_trust_established":False,
            "signed_parity_verified":False,
            "net_profitability_verified":False,**SAFE}

def quote_native(venue, *, rpc, pool, mint_in, amount_in):
    """No fallback to indicative pricing for six complex models."""
    if venue not in VENUE_MODELS:
        raise ValueError("unsupported native swap program")
    if venue=="raydium_cpmm":
        from arb.raydium_cpmm_native_quote import quote_cpmm_exact_input
        return quote_cpmm_exact_input(rpc,pool,mint_in,amount_in)
    raise ValueError("independent "+VENUE_MODELS[venue]+
                     " mathematical quote needs authenticated native "+
                     "fee, ticks/bins and signed-execution parity; no fallback")
