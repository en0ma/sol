"""Diagnostic PumpSwap exact-input output interval across authenticated fee modes.

This is NOT a certified on-chain quote: the fee modes, rounding behavior and
swap instruction execution may differ. Never rank as executable arbitrage.
"""
from arb.pumpswap_fee_modes import compare_fee_modes


def quote_candidate_interval(pool, mint_in, amount_in):
    evidence=compare_fee_modes(pool)
    if (pool.get("verified") is not True or type(amount_in) is not int
            or not 0 < amount_in < 1 << 64):
        raise ValueError("invalid verified pool or trade amount")
    a,b=pool.get("base_mint"),pool.get("quote_mint")
    if not isinstance(a,str) or not isinstance(b,str) or a==b or mint_in not in (a,b):
        raise ValueError("invalid mint direction")
    cfg=pool.get("global_config")
    if not isinstance(cfg,dict):
        raise ValueError("missing same-slot global swap flags")
    sell=mint_in==a
    if cfg.get("sell_enabled" if sell else "buy_enabled") is not True:
        raise ValueError("swap direction disabled or unverified")
    fields=("base_reserve","quote_vault_balance","virtual_quote_reserves",
            "protocol_fees_accrued","creator_fees_accrued")
    if any(type(pool.get(k)) is not int for k in fields):
        raise ValueError("missing accrued-fee reserve accounting")
    base=pool["base_reserve"]
    quote=pool["quote_vault_balance"]+pool["virtual_quote_reserves"]
    spendable=pool["quote_vault_balance"]-pool["protocol_fees_accrued"]-pool["creator_fees_accrued"]
    if min(base,quote,spendable)<=0:
        raise ValueError("invalid priced or spendable reserves")
    rin,rout=(base,quote) if sell else (quote,base)
    outputs={}
    for mode,item in evidence["candidate_modes"].items():
        rates=item["fee_rates"]
        total=sum(rates.values())
        net=amount_in*(10000-total)//10000
        if net<=0:
            raise ValueError("candidate fees consume input")
        output=rout*net//(rin+net)
        if output<=0 or (sell and output>spendable):
            raise ValueError("candidate output unspendable")
        outputs[mode]=output
    if not outputs or evidence["unavailable_modes"]:
        return {"status":"INCOMPLETE_FEE_MODES","candidate_outputs":outputs,
                "unavailable_modes":evidence["unavailable_modes"],
                "actionable":False,"executable_quote":False}
    return {"status":"INDICATIVE_OUTPUT_INTERVAL_ONLY",
            "min_output_base_units":min(outputs.values()),
            "max_output_base_units":max(outputs.values()),
            "candidate_outputs":outputs,
            "fee_modes_equal":evidence["rates_equal"],
            "amount_in":amount_in,"mint_in":mint_in,
            "mint_out":b if sell else a,
            "actionable":False,"executable_quote":False,
            "simulation_verified":False}
