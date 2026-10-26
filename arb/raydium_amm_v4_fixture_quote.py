"""Manifest-backed AMM v4 indicative exact-input quote path.

Reuses pool-native fee, SPL vault balances, and OpenOrders/PnL net reserve
derivation. Inputs are read from a single captured contextual inventory.
Outputs are *indicative* until compared against signed isolated simulations.
"""
from arb.raydium_amm_v4_fee_state import derive_v4,quote_native_fraction
from arb.authenticated_quote_provider import from_snapshot
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
def quote_from_fixture(fixture,*,pool,input_mint,amount_in,observed_unix):
    if type(observed_unix)is not int or observed_unix<0:
        raise ValueError("observation timestamp required")
    report=derive_v4(fixture)
    matching=[r for r in report["pricing"] if r["address"]==pool]
    if len(matching)!=1:
        raise ValueError("AMM v4 pool not in authenticated captured fixture")
    row=matching[0]
    a,b=row["mints"]
    if input_mint not in (a,b):
        raise ValueError("quote input mint mismatch")
    if type(amount_in)is not int or not 0<amount_in<2**64:
        raise ValueError("valid exact input amount required")
    # The quote adapter checks both directions, effective reserves, fee,
    # and market account authentication before computing any output.
    record={"venue":"raydium_amm_v4","address":pool,"mints":row["mints"],
        "slot":row["slot"],"observed_unix":observed_unix,
        "source_authenticated":True,"verified":True,
        "account_owner_verified":True,
        "snapshot_origin":"READ_ONLY_MAINNET_BACKED_SURFPOOL",
        "base_mint":a,"quote_mint":b,
        "trade_fee_ppm":row["trade_fee_ppm"],
        "trade_fee_authenticated":row["trade_fee_authenticated"],
        "market_accounts_authenticated":row["market_accounts_authenticated"],
        "effective_reserves_authenticated":row["effective_reserves_authenticated"],
        "effective_reserves_base_units":row["effective_reserves_base_units"]}
    provider,registry=from_snapshot([record],now=observed_unix)
    if registry["pool_count"]!=1:
        raise ValueError("AMM v4 source snapshot rejected")
    leg={"venue":"raydium_amm_v4","pool":pool,
        "input_mint":input_mint,"output_mint":b if input_mint==a else a}
    quoted=provider(leg,amount_in)
    native=quote_native_fraction(row["effective_reserves_base_units"],row["mints"],
        input_mint,amount_in,row["native_fee_numerator"],row["native_fee_denominator"])
    if native["amount_out"]!=quoted["amount_out"]:
        raise ValueError("AMM v4 native fraction quote and ppm model diverge")
    return {"status":"AMM_V4_ACCOUNT_DERIVED_INDICATIVE_QUOTE",
        "quote":quoted,"snapshot_slot":row["slot"],
        "native_fee_fraction_reference":native,
        "signed_swap_accuracy_verified":False,
        "source_rpc_provenance_independently_attested":False,**SAFE}
