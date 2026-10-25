"""Captured CPMM fee and signed compute evidence, without invented economics."""
from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.fixture_aux_fee_decoder import decode_native_config_fee
from arb.source_snapshot_manifest import verify

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def diagnose(fixture,receipt):
    verify(fixture)
    result={"status":"OFFLINE_PRICING_AND_COST_EVIDENCE",
            "fee_rows":[],"positive_units_consumed":None,
            "start_mint_fee_cost_verified":False,
            "quote_accuracy_verified":False,**SAFE}
    for row in extract_pool_states(fixture):
        if row["venue"]!="raydium_cpmm":
            continue
        item={"venue":row["venue"],"pool":row["address"],
              "source_slot":row["snapshot_slot"],
              "total_effective_fee_authenticated":False}
        try:
            fee=decode_native_config_fee("raydium_cpmm",row["decoded_pool_state"],fixture)
            item.update(config_address=fee["config_address"],
                        trade_fee_ppm=fee["trade_fee_ppm"],
                        creator_fee_ppm=fee["creator_fee_ppm"],
                        trade_fee_authenticated=fee["trade_fee_authenticated"],
                        total_effective_fee_authenticated=fee["total_effective_fee_authenticated"],
                        creator_fee_placement_verified=fee["creator_fee_placement_verified"],
                        effective_quote_fee_ppm=fee.get("effective_quote_fee_ppm"))
            if not fee["total_effective_fee_authenticated"]:
                item["blocker"]="CPMM_CREATOR_FEE_PLACEMENT_UNVERIFIED"
        except (ValueError,KeyError,TypeError) as exc:
            item["blocker"]="CPMM_CAPTURED_CONFIG_INVALID: "+str(exc)[:160]
        result["fee_rows"].append(item)
    if isinstance(receipt,dict):
        units=receipt.get("positive_units_consumed")
        if type(units)is int and 0<units<=1_400_000:
            result["positive_units_consumed"]=units
            result["compute_source"]="SIGNED_OFFLINE_SIMULATE_TRANSACTION_RECEIPT"
        else:
            result["compute_blocker"]="SIGNED_POSITIVE_COMPUTE_MISSING_OR_OVER_LIMIT"
    # Capture a comparable quantity only in units actually measured by the
    # signed RPC simulation. Compute units are not lamports or token costs.
    result["compute_limit_units"]=1_400_000
    result["compute_headroom_units"]=(
        1_400_000-result["positive_units_consumed"]
        if result["positive_units_consumed"] is not None else None)
    # Units consumed do not determine a paid fee; no conversion to start
    # token units is possible without measured fee prices and mint conversion.
    result["priority_fee_lamports_verified"]=False
    result["network_fee_lamports_verified"]=False
    return result
