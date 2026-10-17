"""Conservative PumpSwap fee-mode diagnostic for authenticated account snapshots.

Without on-chain classification of stable/exotic fee modes, compute all
applicable schedules and report ambiguity. Never select a speculative tier
for execution, even when candidate rates happen to agree.
"""
from arb.pumpswap_fee_tiers import select_fee_tier


def compare_fee_modes(pool):
    if not isinstance(pool, dict) or pool.get("canonical_pool_verified") is not True:
        raise ValueError("canonical-pool verification required")
    fee=pool.get("fee_config")
    if not isinstance(fee,dict) or fee.get("account_authenticated") is not True:
        raise ValueError("authenticated FeeConfig required")
    mint_supply=pool.get("base_mint_supply")
    base=pool.get("base_reserve")
    quote=pool.get("quote_vault_balance")
    virtual=pool.get("virtual_quote_reserves")
    if any(type(v) is not int for v in (mint_supply,base,quote,virtual)):
        raise ValueError("incomplete synchronized reserves")
    options={}
    unavailable={}
    canonical=pool.get("canonical")
    if type(canonical) is not bool:
        raise ValueError("unknown canonical status")
    options["standard"]=select_fee_tier(fee,canonical=canonical,
        base_mint_supply=mint_supply,base_reserve=base,quote_reserve=quote+virtual)
    alternate = "stable" if canonical else "exotic"
    alternate_config=({**fee,"fee_tiers":fee.get("stable_fee_tiers")} if canonical
                      else {**fee,"flat_fees":fee.get("exotic_flat_fees")})
    try:
        options[alternate]=select_fee_tier(alternate_config,canonical=canonical,
            base_mint_supply=mint_supply,base_reserve=base,quote_reserve=quote+virtual)
    except ValueError as exc:
        unavailable[alternate]=str(exc)
    rates=[o["fee_rates"] for o in options.values()]
    same=not unavailable and all(item==rates[0] for item in rates[1:])
    return {"status":"MODE_RATES_EQUAL_UNVERIFIED" if same else "FEE_MODE_AMBIGUOUS",
            "candidate_modes":options,"unavailable_modes":unavailable,
            "rates_equal":same,"fee_mode_verified":False,
            "effective_fee_verified":False,"actionable":False}
