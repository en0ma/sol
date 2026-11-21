"""Source-bound PumpSwap fee-tier envelope, not an effective-fee guess.

Canonical fee-program PDA, global config and pool vaults must be captured
together. Every applicable rate candidate is assessed; absent authenticated
market cap or fee mode the answer is a bounded research interval only.
"""
from arb.fixture_pool_fundamentals import extract
from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.pumpswap_fee_account import authenticated_address,decode_authenticated
from arb.pumpswap_global_config import ADDRESS,decode as global_decode
from arb.pumpswap_pool import PROGRAM
from arb.pumpswap_quote import DENOM
from arb.source_snapshot_manifest import verify
import base64
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
def quote_component_rounding_scenarios(*,amount_in,reserve_in,reserve_out,
                                      component_fee_bps,output_liquidity_cap=None):
    """Integer constant-product gross exact-in outputs under fee-rounding modes.

    Each rate comes from authenticated fee account bytes in the caller.
    The independent-component and aggregate fee ceilings are deliberately
    retained as *possible outcomes*, not a claim of source-exact execution.
    """
    if (any(type(x)is not int for x in (amount_in,reserve_in,reserve_out))
            or not 0<amount_in<2**64 or not 0<reserve_in<2**64
            or not 0<reserve_out<2**64 or
            not isinstance(component_fee_bps,(list,tuple)) or
            len(component_fee_bps)!=3 or
            any(type(x)is not int or x<0 for x in component_fee_bps)
            or sum(component_fee_bps)>=10000 or
            (output_liquidity_cap is not None and
             (type(output_liquidity_cap)is not int or
              not 0<output_liquidity_cap<=reserve_out))):
        raise ValueError("invalid source PumpSwap reserves or native fee components")
    rates=[v*100 for v in component_fee_bps]
    rate=sum(rates)
    aggregate_ceil=(amount_in*rate+DENOM-1)//DENOM
    aggregate_floor=amount_in*rate//DENOM
    independent_ceil=sum((amount_in*x+DENOM-1)//DENOM for x in rates)
    results=[]
    for mode,deduction in (("AGGREGATE_CEIL",aggregate_ceil),
                           ("COMPONENT_CEIL",independent_ceil),
                           ("AGGREGATE_FLOOR",aggregate_floor)):
        net=amount_in-deduction
        if net<=0:
            continue
        output=reserve_out*net//(reserve_in+net)
        if output<=0 or output>=reserve_out:
            continue
        if output_liquidity_cap is not None and output>output_liquidity_cap:
            continue
        results.append({"rounding_mode":mode,"fee_input_base_units":deduction,
                        "modeled_output_base_units":output})
    if not results:
        raise ValueError("source PumpSwap fees or liquidity prevent an exact-in fill")
    return {"modeled_outputs":results,
            "minimum_modeled_output_base_units":min(
                x["modeled_output_base_units"] for x in results),
            "maximum_modeled_output_base_units":max(
                x["modeled_output_base_units"] for x in results),
            "aggregate_ceiling_fee_units":aggregate_ceil,
            "aggregate_floor_fee_units":aggregate_floor,
            "component_ceiling_fee_units":independent_ceil,
            "effective_fee_rounding_verified":False,
            "protocol_exact_verified":False,**SAFE}

def quote_fee_candidates(fixture,*,pool,mint_in,amount_in):
    if type(amount_in)is not int or not 0<amount_in<2**64 or any(fixture.get(k)is not False for k in SAFE):
        raise ValueError("safe integer source amount required")
    verify(fixture)
    rows=extract_pool_states(fixture)
    row=next((r for r in rows if r["venue"]=="pumpswap" and r["address"]==pool),None)
    if row is None:raise ValueError("PumpSwap source pool absent")
    state=row["decoded_pool_state"]
    included=set(fixture["state_account_addresses"])
    fee_address,_=authenticated_address()
    if fee_address not in included or ADDRESS not in included:
        raise ValueError("canonical fee and global config not present in same-slot source manifest")
    if fee_address not in fixture["accounts"] or ADDRESS not in fixture["accounts"]:
        raise ValueError("canonical fee or global account bytes missing")
    fee=decode_authenticated(fixture["accounts"][fee_address],address=fee_address)
    account=fixture["accounts"][ADDRESS]
    if account.get("owner")!=PROGRAM or account.get("executable") is not False:
        raise ValueError("unauthenticated PumpSwap global config")
    encoded=account.get("data")
    if not isinstance(encoded,list) or len(encoded)!=2 or encoded[1]!="base64":
        raise ValueError("untrusted global configuration bytes")
    global_state=global_decode(base64.b64decode(encoded[0],validate=True))
    fundamentals=next((x for x in extract(fixture)["fundamentals"] if x["address"]==pool),None)
    if fundamentals is None:raise ValueError("PumpSwap SPL vault evidence absent")
    base,quote=fundamentals["vault_base_units"]
    # Earlier PumpSwap Pool versions predate appended fee counters.
    # Official PumpSwap account compatibility treats absent trailing fields
    # as zero, never as unvalidated liquidity or a fabricated fee tier.
    pfee=state.get("protocol_fees")
    cfee=state.get("creator_fees")
    if pfee is None:pfee=0
    if cfee is None:cfee=0
    if type(pfee)is not int or type(cfee)is not int:
        raise ValueError("PumpSwap accrued fee counters malformed")
    accrued=pfee+cfee
    virtual=state["virtual_quote_reserves"]
    if any(type(x)is not int for x in (base,quote,accrued,virtual)) or min(base,quote)<=0 or accrued<0 or accrued>=quote or quote+virtual<=0:
        raise ValueError("invalid source PumpSwap fee liabilities")
    base_mint,quote_mint=state["base_mint"],state["quote_mint"]
    if mint_in not in (base_mint,quote_mint):raise ValueError("PumpSwap input direction mismatch")
    from_base=mint_in==base_mint
    if not global_state["sell_enabled" if from_base else "buy_enabled"]:
        raise ValueError("source PumpSwap direction disabled")
    pricing_quote=quote+virtual
    spent_quote=quote-accrued
    r_in,r_out=(base,pricing_quote) if from_base else (pricing_quote,base)
    candidates=[("global",global_state)]
    for name,fees in (("flat",fee["flat_fees"]),("exotic",fee["exotic_flat_fees"])):
        candidates.append((name,fees))
    for kind,tiers in (("standard",fee["fee_tiers"]),("stable",fee["stable_fee_tiers"])):
        candidates.extend((kind+":"+str(t["market_cap_threshold"]),t["fees"]) for t in tiers)
    # The canonical source mint account supplies actual decimals. The
    # source fee tier's threshold is in the corresponding quote base unit.
    selected=None
    if base_mint in included and base_mint in fixture["accounts"]:
        from arb.pumpswap_source_tier_selector import (
            choose_tier_by_source_market_cap,mint_decimals_from_account)
        mint_account=fixture["accounts"][base_mint]
        from arb.token_vaults import TOKEN_PROGRAM
        encoded_mint=mint_account.get("data")
        if (mint_account.get("owner")==TOKEN_PROGRAM and
                mint_account.get("executable") is False and
                isinstance(encoded_mint,list) and len(encoded_mint)==2 and
                encoded_mint[1]=="base64"):
            raw_mint=base64.b64decode(encoded_mint[0],validate=True)
            decimals=mint_decimals_from_account(raw_mint)
            actual_supply=int.from_bytes(raw_mint[36:44],"little")
            selected=choose_tier_by_source_market_cap(
                pool_state=state,fee_config=fee,
                base_reserve=base,quote_reserve=quote,
                base_decimals=decimals,
                base_supply_base_units=actual_supply)
    if selected is not None and selected.get("tier_selected") is True:
        candidates=[("selected_onchain_source_tier",selected["fees"])]
    outcomes=[]
    for name,fees in candidates:
        values=[fees[k] for k in ("lp_fee_bps","protocol_fee_bps")]+[
            fees.get("creator_fee_bps",fees.get("coin_creator_fee_bps"))]
        if any(type(v)is not int or v<0 for v in values):
            raise ValueError("malformed account-derived PumpSwap fee tier")
        rate=sum(values)*100
        if rate>=DENOM:raise ValueError("PumpSwap fee tier exhausts input")
        try:
            model=quote_component_rounding_scenarios(
                amount_in=amount_in,reserve_in=r_in,reserve_out=r_out,
                component_fee_bps=values,
                output_liquidity_cap=spent_quote if from_base else None)
        except ValueError:
            continue
        conservative=next((x["modeled_output_base_units"]
            for x in model["modeled_outputs"]
            if x["rounding_mode"]=="AGGREGATE_CEIL"),None)
        if conservative is None:
            continue
        outcomes.append({"tier":name,"total_fee_ppm":rate,
                         "amount_out":conservative,
                         "component_ceiling_fee_units":model["component_ceiling_fee_units"],
                         "aggregate_ceiling_fee_units":model["aggregate_ceiling_fee_units"],
                         "aggregate_floor_fee_units":model["aggregate_floor_fee_units"],
                         "modeled_output_rounding_low":model["minimum_modeled_output_base_units"],
                         "modeled_output_rounding_high":model["maximum_modeled_output_base_units"],
                         "fee_rounding_is_protocol_verified":False})
    if not outcomes:
        return {"status":"PUMPSWAP_SOURCE_FEE_CANDIDATES_CANNOT_FILL",
                "source_slot":fixture["state_accounts_observed_slot"],
                "effective_fee_verified":False,"protocol_exact_verified":False,**SAFE}
    return {"status":"PUMPSWAP_SOURCE_FEE_TIER_SCENARIOS_NOT_EXHAUSTIVE",
            "source_slot":fixture["state_accounts_observed_slot"],"pool":pool,
            "input_mint":mint_in,"amount_in":amount_in,
            "candidate_count":len(outcomes),"candidates":outcomes,
            "canonical_source_tier_selection":selected,
            "fee_mode_selected_from_source":selected is not None and selected.get("tier_selected") is True,
            "minimum_candidate_output":min(x["amount_out"] for x in outcomes),
            "maximum_candidate_output":max(x["amount_out"] for x in outcomes),
            "minimum_rounding_scenario_output":min(
                x["modeled_output_rounding_low"] for x in outcomes),
            "maximum_rounding_scenario_output":max(
                x["modeled_output_rounding_high"] for x in outcomes),
            "all_possible_fee_modes_exhaustively_verified":False,
            "effective_fee_verified":False,"protocol_exact_verified":False,**SAFE}
