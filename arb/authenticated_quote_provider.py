"""M5 authenticated CPMM, CLMM and Orca within-tick exact-input models.

Other venues explicitly fail closed until their directional fee/liquidity
models are integrated. No mock swap amounts, inferred fee tiers, or live RPC.
"""
from arb.cpmm_quote import quote_exact_input
from arb.raydium_clmm_within_tick_quote import quote_within_tick
from arb.orca_spot_quote import quote_bounded_single_tick
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
        if venue=="orca":
            if state.get("tick_bounds_authenticated") is not True or state.get("trade_fee_authenticated") is not True:
                raise ValueError("Orca tick bounds and fee must be authenticated")
            if (state.get("token_mint_a"),state.get("token_mint_b"))!=tuple(state["mints"]):
                raise ValueError("Orca onchain mint orientation mismatch")
            if (leg.get("input_mint"),leg.get("output_mint")) not in (
                (state["mints"][0],state["mints"][1]),(state["mints"][1],state["mints"][0])):
                raise ValueError("Orca route mint direction invalid")
            fee=state.get("fee_rate_hundredths_bps")
            lower,upper=state.get("lower_sqrt_x64"),state.get("upper_sqrt_x64")
            if type(fee)is not int or not 0<=fee<1000000 or type(lower)is not int or type(upper)is not int:
                raise ValueError("Orca authenticated fee and tick price bounds required")
            sizes=state.get("max_within_tick_input_by_mint")
            if not isinstance(sizes,dict) or type(sizes.get(leg["input_mint"])) is not int or sizes[leg["input_mint"]]<=0:
                raise ValueError("Orca authenticated directional input budget missing")
            raw=quote_bounded_single_tick(state,leg["input_mint"],amount_in,
                lower_sqrt_x64=lower,upper_sqrt_x64=upper)
            result={"venue":venue,"pool":pool,"input_mint":leg["input_mint"],
                "output_mint":leg["output_mint"],"amount_in":amount_in,
                "amount_out":raw["estimated_output_base_units"],
                "fee_input_units":(amount_in*fee+999999)//1000000,
                "liquidity_input_units":sizes[leg["input_mint"]],
                "price_impact_bps":min(10000,(amount_in*10000+sizes[leg["input_mint"]]-1)//sizes[leg["input_mint"]]),
                "snapshot_slot":state["slot"],"observed_unix":state["observed_unix"],
                "source_authenticated":True,"quote_source":"AUTHENTICATED_POOL_SNAPSHOT",
                "quote_model":"ORCA_WHIRLPOOL_AUTHENTICATED_WITHIN_TICK_INDICATIVE"}
            assessment=validate(result,state,requested_input=amount_in,now=now,max_age=max_age)
            if assessment["status"]!="VALIDATED_INDICATIVE_QUOTE":
                raise ValueError("Orca quote rejected: "+", ".join(assessment["reason_codes"]))
            return result
        if venue=="raydium_clmm":
            if state.get("trade_fee_authenticated") is not True or state.get("tick_boundary_authenticated") is not True:
                raise ValueError("CLMM fee and directional tick boundary must be authenticated")
            fee=state.get("trade_fee_ppm")
            if type(fee)is not int:
                raise ValueError("CLMM authenticated fee required")
            if (leg.get("input_mint"),leg.get("output_mint")) not in (
                (state["mints"][0],state["mints"][1]),
                (state["mints"][1],state["mints"][0])):
                raise ValueError("CLMM mint direction invalid")
            if (state.get("token_mint_0"),state.get("token_mint_1"))!=tuple(state["mints"]):
                raise ValueError("CLMM onchain orientation mismatch")
            bound=state.get("next_initialized_sqrt_by_input_mint")
            if not isinstance(bound,dict) or type(bound.get(leg["input_mint"])) is not int:
                raise ValueError("authenticated directional CLMM tick boundary missing")
            size=state.get("max_within_tick_input_by_mint")
            if not isinstance(size,dict) or type(size.get(leg["input_mint"])) is not int or size[leg["input_mint"]]<=0:
                raise ValueError("authenticated directional CLMM input budget missing")
            raw=quote_within_tick(state,leg["input_mint"],amount_in,fee,bound[leg["input_mint"]])
            result={"venue":venue,"pool":pool,
                "input_mint":leg["input_mint"],"output_mint":leg["output_mint"],
                "amount_in":amount_in,"amount_out":raw["estimated_output_base_units"],
                "fee_input_units":(amount_in*fee+999999)//1000000,
                "liquidity_input_units":size[leg["input_mint"]],
                "price_impact_bps":min(10000,(amount_in*10000+size[leg["input_mint"]]-1)//size[leg["input_mint"]]),
                "snapshot_slot":state["slot"],"observed_unix":state["observed_unix"],
                "source_authenticated":True,"quote_source":"AUTHENTICATED_POOL_SNAPSHOT",
                "quote_model":"RAYDIUM_CLMM_AUTHENTICATED_WITHIN_TICK_INDICATIVE"}
            assessment=validate(result,state,requested_input=amount_in,now=now,max_age=max_age)
            if assessment["status"]!="VALIDATED_INDICATIVE_QUOTE":
                raise ValueError("CLMM quote rejected: "+", ".join(assessment["reason_codes"]))
            return result
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
