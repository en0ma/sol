"""Conservatively project manifest-verified native data into quote model inputs.

Only pool-native Orca Whirlpool fee is independently available here.
All other dynamic/config fee and segment models remain blocked. This adapter
never labels external aux pricing as source-authenticated.
"""
from arb.fixture_pool_fundamentals import extract
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
def derive(fixture):
    batch=extract(fixture)
    out=[];blocked=[]
    for f in batch["fundamentals"]:
        venue=f["venue"]
        common={"venue":venue,"address":f["address"],"mints":f["mints"],
                "slot":f["snapshot_slot"],"vault_base_units":f["vault_base_units"]}
        if venue=="orca":
            fee=f["fee_rate_hundredths_bps"]
            # Whirlpool fee rate units are hundredths of bps: exactly ppm.
            if type(fee)is not int or not 0<=fee<1000000 or f.get("fee_rate_read_from_native_pool") is not True:
                raise ValueError("Orca pool-native trade fee not authenticated")
            common.update(trade_fee_authenticated=True,trade_fee_ppm=fee,
                          fee_source="NATIVE_WHIRLPOOL_POOL_ACCOUNT",
                          liquidity=f["liquidity"],sqrt_price_x64=f["sqrt_price_x64"])
            out.append(common)
            # No tick-array-derived boundaries: quote must STILL fail closed.
            blocked.append({"venue":venue,"pool":f["address"],
                "missing":["authenticated directional tick bounds","directional input limit"]})
        else:
            common.update(trade_fee_authenticated=False)
            out.append(common)
            blocked.append({"venue":venue,"pool":f["address"],
                "missing":["effective fee derived from captured config accounts",
                           "directional price segment and/or adjusted reserves"]})
    return {"status":"PARTIAL_NATIVE_QUOTE_STATE",
            "native_states":out,"remaining_pricing_gates":blocked,
            "all_venue_quotes_ready":False,"quote_accuracy_verified":False,**SAFE}
