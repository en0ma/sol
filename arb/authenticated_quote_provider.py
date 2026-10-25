"""M5 first real venue-math integration: authenticated Raydium CPMM exact-input.

All other venues explicitly fail closed until their directional fee/liquidity
models are integrated. No mock swap amounts, inferred fee tiers, or live RPC.
"""
from arb.cpmm_quote import quote_exact_input
from arb.venue_quote_contract import validate
from arb.market_state_registry import normalize

def from_snapshot(snapshot,*,now,max_age=60,max_slot_skew=32):
    registry=normalize(snapshot,as_of_unix=now,max_age_seconds=max_age,
                       max_slot_skew=max_slot_skew)
    by_key={(x["venue"],x["address"]):x for x in registry["pools"]}
    def quote(leg,amount_in):
        if not isinstance(leg,dict):
            raise ValueError("invalid route leg")
        venue,pool=leg.get("venue"),leg.get("pool")
        state=by_key.get((venue,pool))
        if state is None:
            raise ValueError("pool not in authenticated snapshot")
        if type(amount_in)is not int or not 0<amount_in<2**64:
            raise ValueError("exact-input amount required")
        if venue!="raydium_cpmm":
            raise ValueError("venue amount-aware model not integrated: "+str(venue))
        if state.get("trade_fee_authenticated") is not True:
            raise ValueError("onchain trade fee not authenticated")
        fee=state.get("trade_fee_ppm")
        reserves=state.get("vault_base_units")
        mints=state["mints"]
        if (type(fee)is not int or not 0<=fee<1000000 or
                not isinstance(reserves,list) or len(reserves)!=2 or
                any(type(v)is not int or v<=0 for v in reserves)):
            raise ValueError("CPMM authenticated fee/reserve state incomplete")
        if (leg.get("input_mint"),leg.get("output_mint")) not in (
            (mints[0],mints[1]),(mints[1],mints[0])):
            raise ValueError("CPMM route direction invalid")
        idx=mints.index(leg["input_mint"])
        raw=quote_exact_input(reserves[idx],reserves[1-idx],amount_in,fee)
        # Conservatively bound indicative size to authenticated input reserve.
        result={"venue":venue,"pool":pool,"input_mint":mints[idx],
                "output_mint":mints[1-idx],"amount_in":amount_in,
                "amount_out":raw["estimated_output_base_units"],
                "fee_input_units":raw["estimated_fee_base_units"],
                "liquidity_input_units":reserves[idx],
                "price_impact_bps":min(10000,(amount_in*10000+reserves[idx]-1)//reserves[idx]),
                "snapshot_slot":state["slot"],
                "observed_unix":state["observed_unix"],
                "source_authenticated":True,
                "quote_source":"AUTHENTICATED_POOL_SNAPSHOT",
                "quote_model":"RAYDIUM_CPMM_CONSTANT_PRODUCT_INDICATIVE"}
        assessment=validate(result,state,requested_input=amount_in,now=now,max_age=max_age)
        if assessment["status"]!="VALIDATED_INDICATIVE_QUOTE":
            raise ValueError("CPMM quote rejected: "+", ".join(assessment["reason_codes"]))
        return result
    return quote,registry
