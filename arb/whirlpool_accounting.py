"""Conservative mark-to-market of simulated WSOL/USDC holdings.

An on-chain spot mark is NOT an executable liquidation quote. This module
never approves live execution based on a mark. Integer arithmetic ensures
rounding favors the conservative side. All estimates are explicitly labeled.
"""
from decimal import Decimal, localcontext, ROUND_FLOOR

Q64=1<<64
SCALE=1_000_000_000

def mark_residual_usdc_lamports(usdc_base_units, state, haircut_bps=100):
    if type(usdc_base_units) is not int or usdc_base_units<0:
        raise ValueError("invalid residual")
    if type(haircut_bps) is not int or not 0<=haircut_bps<10000:
        raise ValueError("invalid haircut")
    sqrt=int(state["sqrt_price_x64"])
    fee=int(state["fee_rate_hundredths_bps"])
    if sqrt<=0 or not 0<=fee<1000000:
        raise ValueError("invalid Whirlpool price or fee")
    # sqrt_price ** 2 = token B base units per token A base unit.
    with localcontext() as context:
        context.prec=80
        b_per_a=(Decimal(sqrt)/Decimal(Q64))**2
        usdc_per_wsol=b_per_a if state["token_mint_a"].startswith("So111") else Decimal(1)/b_per_a
        # WSOL base units per USDC base unit = inverse of USDC per WSOL.
        native=Decimal(usdc_base_units)/usdc_per_wsol
        native *= Decimal(1000000-fee)/Decimal(1000000)
        native *= Decimal(10000-haircut_bps)/Decimal(10000)
        return int(native.to_integral_value(rounding=ROUND_FLOOR))

def assess(stats,state,minimum_profit_lamports=10000,haircut_bps=100):
    if type(minimum_profit_lamports) is not int or minimum_profit_lamports<0:
        raise ValueError("invalid minimum profit")
    for key in ("start_wsol_lamports","end_wsol_lamports","residual_usdc_base_units"):
        if type(stats.get(key)) is not int or stats[key]<0:
            raise ValueError("missing verified token balances")
    fee=stats.get("estimated_network_fee_lamports")
    if type(fee) is not int or fee<0:
        return {"status":"UNPRICED_NETWORK_FEE","execution_approved":False}
    residual=mark_residual_usdc_lamports(stats["residual_usdc_base_units"],state,haircut_bps)
    observed=stats["end_wsol_lamports"]-stats["start_wsol_lamports"]-fee
    marked=observed+residual
    return {"status":"MARKED_ONLY","execution_approved":False,
            "observed_wsol_delta_after_fee_lamports":observed,
            "residual_usdc_mark_lamports":residual,
            "indicative_marked_pnl_lamports":marked,
            "minimum_profit_lamports":minimum_profit_lamports,
            "mark_above_threshold":marked>=minimum_profit_lamports,
            "haircut_bps":haircut_bps,
            "warning":"Residual valuation is spot-derived, not executable; no profit or live-trade approval"}
