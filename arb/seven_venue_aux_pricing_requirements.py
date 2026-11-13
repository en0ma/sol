"""Seven-venue missing auxiliary-account inputs for executable quote parity.

Builds strict structured gaps from manifest-backed native fundamentals. This
is NOT a complete config/bin/market decoder: only native verified fields may
be promoted and none of the derived records authorizes signed trade execution.
"""
from arb.fixture_native_quote_state import derive
from arb.execution_target_matrix import TARGET_VENUES
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
REQUIRED={
"orca":("authenticated_directional_tick_bounds","max_within_tick_input_by_mint"),
"raydium_cpmm":("amm_config_trade_fee_ppm",),
"raydium_clmm":("amm_config_trade_fee_ppm","authenticated_directional_tick_bounds","max_within_tick_input_by_mint"),
"meteora_dlmm":("active_bin_array_price_q64","active_bin_reserves","dynamic_fee_ppm","max_within_segment_input_by_mint"),
"meteora_damm_v2":("config_dynamic_fee_ppm","authenticated_price_segment_bound","max_within_segment_input_by_mint"),
"pumpswap":("global_config_protocol_fee_ppm","fee_program_effective_fee_ppm","verified_virtual_and_spendable_reserves"),
"raydium_amm_v4":("amm_v4_trade_fee_ppm","open_orders_balances","net_pnl_adjusted_effective_reserves")
}
if set(REQUIRED)!=set(TARGET_VENUES):
    raise RuntimeError("missing active venue auxiliary pricing checklist")
def requirements(fixture):
    native=derive(fixture)
    rows=[]
    for state in native["native_states"]:
        venue=state["venue"]
        rows.append({"venue":venue,"pool":state["address"],
            "snapshot_slot":state["slot"],
            "required_independent_account_derivations":list(REQUIRED[venue]),
            "completed_independent_account_derivations":[],
            "full_fee_and_liquidity_authenticated":False,
            "source_pool_native_fee_authenticated":state.get("trade_fee_authenticated") is True})
    return {"status":"SEVEN_VENUE_AUXILIARY_PRICING_GAPS",
        "venue_count":len(rows),
        "account_derived_auxiliary_models_verified":0,
        "rows":rows,"quote_accuracy_verified":False,**SAFE}
