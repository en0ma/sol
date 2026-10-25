"""Offline auxiliary config-account fee extraction from manifest-captured bytes.

CPMM and CLMM configurations use existing protocol layout decoders. This
extractor must never fetch RPC data, guess fee tiers, or accept config metadata
supplied independently of the pool's decoded on-chain config address.
Other five venues remain blocked for complete auxiliary pricing.
"""
import base64
from arb.cpmm_config import decode_amm_config
from arb.raydium_clmm_fee_snapshot import DISC as CLMM_DISC
from arb.raydium_cpmm import PROGRAM as CPMM_PROGRAM
from arb.raydium_clmm import PROGRAM as CLMM_PROGRAM
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def _config_bytes(fixture,address,owner):
    if address not in fixture["state_account_addresses"]:
        raise ValueError("configuration not in contextual source inventory")
    info=fixture["accounts"].get(address)
    if not isinstance(info,dict) or info.get("owner")!=owner or info.get("executable") is not False:
        raise ValueError("configuration account owner not authenticated")
    data=info.get("data")
    if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
        raise ValueError("invalid configuration account encoding")
    return base64.b64decode(data[0],validate=True)

def decode_native_config_fee(venue,state,fixture):
    if venue=="raydium_cpmm":
        address=state["amm_config"]
        cfg=decode_amm_config(_config_bytes(fixture,address,CPMM_PROGRAM))
        # Creator fee treatment is version/direction dependent; refuse
        # false effective-fee authentication even when trade fee is decoded.
        return {"venue":venue,"config_address":address,
            "trade_fee_ppm":cfg["trade_fee_rate_ppm"],
            "creator_fee_ppm":cfg["creator_fee_rate_ppm"],
            "trade_fee_authenticated":True,
            "total_effective_fee_authenticated":cfg["creator_fee_rate_ppm"]==0,
            "effective_quote_fee_ppm":cfg["trade_fee_rate_ppm"] if cfg["creator_fee_rate_ppm"]==0 else None,
            "creator_fee_placement_verified":False,**SAFE}
    if venue=="raydium_clmm":
        address=state["amm_config"]
        raw=_config_bytes(fixture,address,CLMM_PROGRAM)
        if len(raw)<53 or raw[:8]!=CLMM_DISC:
            raise ValueError("invalid CLMM config layout")
        spacing=int.from_bytes(raw[51:53],"little")
        fee=int.from_bytes(raw[47:51],"little")
        if spacing!=state["tick_spacing"] or not 0<=fee<1000000:
            raise ValueError("CLMM pool tick spacing/config trade fee mismatch")
        return {"venue":venue,"config_address":address,
            "trade_fee_ppm":fee,"trade_fee_authenticated":True,
            "total_effective_fee_authenticated":True,
            "effective_quote_fee_ppm":fee,**SAFE}
    raise ValueError("fee config decoder not independently implemented for "+str(venue))
