"""PumpSwap canonical fee-tier selector with source-backed market capitalization.

Pump documentation defines tier market cap as reserve-implied quote-token
price multiplied by one billion base tokens. Work entirely in smallest
quote-token units; no floating-point division. Authentication is performed by
the calling source fixture and canonical PDA verifier. Specialized mayhem,
cashback, custom-creator and protocol overrides remain separate gates.
"""
from arb.pumpswap_pool import NATIVE_WSOL_MINT
from arb.pumpswap_canonical import classify_pool
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
USDC="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
BASE_SUPPLY_HUMAN=1_000_000_000

def mint_decimals_from_account(raw):
    if type(raw)is not bytes or len(raw)!=82 or raw[45]!=1:
        raise ValueError("only initialized classic SPL mint bytes supported")
    decimals=raw[44]
    if decimals>18:raise ValueError("unsupported base decimals")
    return decimals

def market_cap_quote_base_units(*,base_reserve,quote_reserve,
                                virtual_quote_reserves,base_decimals,
                                base_supply_base_units=None):
    inputs=(base_reserve,quote_reserve,virtual_quote_reserves,base_decimals)
    if any(type(v)is not int for v in inputs) or base_reserve<=0 or quote_reserve<=0:
        raise ValueError("positive native pool token reserves required")
    if not 0<=base_decimals<=18:
        raise ValueError("untrusted base mint decimal precision")
    effective=quote_reserve+virtual_quote_reserves
    if effective<=0:
        raise ValueError("effective quoted liquidity is nonpositive")
    if base_supply_base_units is not None and (
            type(base_supply_base_units)is not int or base_supply_base_units<=0):
        raise ValueError("native source base mint supply invalid")
    supply=(BASE_SUPPLY_HUMAN*10**base_decimals
            if base_supply_base_units is None else base_supply_base_units)
    market_cap=effective*supply//base_reserve
    return {"market_cap_quote_base_units":market_cap,
            "reserve_implied_price_numerator":effective,
            "reserve_implied_price_denominator":base_reserve,
            "base_decimals":base_decimals,
            "source_mint_supply_authenticated":base_supply_base_units is not None,
            "quote_base_units":True,**SAFE}

def choose_tier_by_source_market_cap(*,pool_state,fee_config,
                                      base_reserve,quote_reserve,
                                      base_decimals,base_supply_base_units=None):
    if not isinstance(pool_state,dict) or not isinstance(fee_config,dict):
        raise ValueError("PumpSwap native state and fee configuration required")
    if fee_config.get("account_authenticated") is not True:
        raise ValueError("fee program account not independently authenticated")
    canonical=classify_pool(pool_state)
    base_mint=pool_state.get("base_mint")
    quote_mint=pool_state.get("quote_mint")
    if not canonical["canonical"]:
        fees=fee_config.get("flat_fees")
        if not isinstance(fees,dict):
            raise ValueError("noncanonical PumpSwap native flat fee unavailable")
        return {"status":"PUMP_NONCANONICAL_SOURCE_FLAT_FEE",
                "tier_selected":True,"fees":fees,
                "selected_total_fee_bps":sum(fees.values()),
                "source_tier_account_authenticated":True,
                "onchain_fee_rounding_parity_verified":False,
                "protocol_exact_verified":False,**SAFE}
    if quote_mint not in (NATIVE_WSOL_MINT,USDC):
        fees=fee_config.get("exotic_flat_fees")
        if not isinstance(fees,dict):
            raise ValueError("custom quote PumpSwap native exotic fee unavailable")
        if pool_state.get("creator_fee_bps",0):
            return {"status":"PUMP_CUSTOM_CREATOR_FEE_REQUIRES_POOL_OVERRIDE",
                    "tier_selected":False,**SAFE}
        return {"status":"PUMP_CUSTOM_QUOTE_SOURCE_FLAT_FEE",
                "tier_selected":True,"fees":fees,
                "selected_total_fee_bps":sum(fees.values()),
                "source_tier_account_authenticated":True,
                "onchain_fee_rounding_parity_verified":False,
                "protocol_exact_verified":False,**SAFE}
    if base_mint==NATIVE_WSOL_MINT:
        raise ValueError("unsupported PumpSwap canonical base mint is WSOL")
    if type(base_supply_base_units)is not int or base_supply_base_units<=0:
        raise ValueError("source-authenticated canonical base mint supply required")
    if pool_state.get("is_mayhem_mode") not in (0,1) or pool_state.get("is_cashback_coin") not in (0,1):
        raise ValueError("PumpSwap source mode flags not available")
    if pool_state["is_mayhem_mode"] or pool_state["is_cashback_coin"]:
        return {"status":"PUMP_FEE_MODE_SPECIAL_ROUTING_UNSUPPORTED",
                "tier_selected":False,**SAFE}
    market=market_cap_quote_base_units(
        base_reserve=base_reserve,quote_reserve=quote_reserve,
        virtual_quote_reserves=pool_state.get("virtual_quote_reserves"),
        base_decimals=base_decimals,
        base_supply_base_units=base_supply_base_units)
    stable=quote_mint==USDC
    tiers=fee_config.get("stable_fee_tiers" if stable else "fee_tiers")
    if not isinstance(tiers,list) or not tiers:
        raise ValueError("canonical PumpSwap effective fee tier list empty")
    previous=-1
    selected=None
    for tier in tiers:
        threshold=tier.get("market_cap_threshold")
        fees=tier.get("fees")
        if (type(threshold)is not int or threshold<=previous
                or not isinstance(fees,dict) or
                any(type(fees.get(k))is not int or not 0<=fees[k]<=10000
                    for k in ("lp_fee_bps","protocol_fee_bps","creator_fee_bps"))):
            raise ValueError("invalid authenticated PumpSwap fee config tier")
        previous=threshold
        if market["market_cap_quote_base_units"]>=threshold:
            selected=(threshold,fees)
        else:
            break
    if selected is None:
        raise ValueError("no matching floor fee tier in source account")
    threshold,fees=selected
    return {"status":"PUMP_CANONICAL_SOURCE_MARKET_CAP_TIER_SELECTED",
            "tier_selected":True,"quote_asset":"USDC" if stable else "WSOL",
            "market_cap_quote_base_units":market["market_cap_quote_base_units"],
            "selected_threshold_quote_base_units":threshold,
            "fees":fees,
            "selected_total_fee_bps":sum(fees.values()),
            "source_tier_account_authenticated":True,
            "onchain_fee_rounding_parity_verified":False,
            "protocol_exact_verified":False,**SAFE}
