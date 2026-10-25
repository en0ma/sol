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
                        creator_fee_placement_verified=fee["creator_fee_placement_verified"])
            if not fee["total_effective_fee_authenticated"]:
                item["blocker"]="CPMM_CREATOR_FEE_PLACEMENT_UNVERIFIED"
        except (ValueError,KeyError,TypeError) as exc:
            item["blocker"]="CPMM_CAPTURED_CONFIG_INVALID: "+str(exc)[:160]
        result["fee_rows"].append(item)
    if isinstance(receipt,dict):
        units=receipt.get("positive_units_consumed")
        if type(units)is int and units>=0:
            result["positive_units_consumed"]=units
        else:
            result["compute_blocker"]="POSITIVE_COMPUTE_UNAVAILABLE"
    return result
