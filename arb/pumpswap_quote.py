"""Amount-aware PumpSwap reserve quoting, requiring caller-verified fee state.

PumpSwap v2 can have signed virtual quote reserves and protocol/creator fee
buckets still present in the quote vault. Never infer spendable quote liquidity
from the raw vault balance or assume a default fee tier. Indicative only:
exact pump-fees rounding and on-chain swap execution remain unverified.
See @pump-fun/pump-swap-sdk and pump-fun/pump-public-docs.
"""
DENOM = 1_000_000


def quote_exact_input(pool, mint_in, amount_in, *, verified_total_fee_ppm):
    if not isinstance(pool, dict) or pool.get("venue") != "pumpswap":
        raise ValueError("unsupported PumpSwap pool")
    if pool.get("verified") is not True or pool.get("fee_verified_onchain") is not True:
        raise ValueError("pool and fee configuration must be verified on-chain")
    if type(amount_in) is not int or not 0 < amount_in < 1 << 64:
        raise ValueError("invalid exact input")
    if type(verified_total_fee_ppm) is not int or not 0 <= verified_total_fee_ppm < DENOM:
        raise ValueError("invalid verified fee rate")
    fields=("base_reserve", "quote_vault_balance", "virtual_quote_reserves",
            "protocol_fees_accrued", "creator_fees_accrued")
    if any(type(pool.get(f)) is not int for f in fields):
        raise ValueError("incomplete integer reserve or fee bucket state")
    base = pool["base_reserve"]
    quote_vault = pool["quote_vault_balance"]
    virtual = pool["virtual_quote_reserves"]
    accrued = pool["protocol_fees_accrued"] + pool["creator_fees_accrued"]
    if base <= 0 or quote_vault <= 0 or accrued < 0 or accrued > quote_vault:
        raise ValueError("invalid physical reserves or accrued fees")
    priced_quote = quote_vault + virtual
    spendable_quote = quote_vault - accrued
    if priced_quote <= 0 or spendable_quote <= 0:
        raise ValueError("invalid effective or spendable quote reserves")
    base_mint, quote_mint = pool.get("base_mint"), pool.get("quote_mint")
    if not isinstance(base_mint, str) or not isinstance(quote_mint, str) or base_mint == quote_mint:
        raise ValueError("invalid pool mints")
    if mint_in not in (base_mint, quote_mint):
        raise ValueError("input mint not in pool")
    from_base = mint_in == base_mint
    reserve_in, reserve_out = (base, priced_quote) if from_base else (priced_quote, base)
    net = amount_in * (DENOM - verified_total_fee_ppm) // DENOM
    if net <= 0:
        raise ValueError("input eaten by fees")
    output = reserve_out * net // (reserve_in + net)
    if output <= 0 or output >= reserve_out:
        raise ValueError("dust or empty output")
    if from_base and output > spendable_quote:
        raise ValueError("sell output exceeds spendable physical quote reserve")
    return {"venue": "pumpswap", "mint_in": mint_in,
            "mint_out": quote_mint if from_base else base_mint,
            "amount_in": amount_in, "estimated_output_base_units": output,
            "effective_quote_reserve": priced_quote,
            "spendable_quote_reserve": spendable_quote,
            "fee_rate_ppm": verified_total_fee_ppm,
            "status": "INDICATIVE_PUMPSWAP_ONLY", "actionable": False,
            "executable_quote": False, "simulation_verified": False}
