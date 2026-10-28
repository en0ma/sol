"""Decode DAMM v2 source PoolFeesStruct from 1112-byte on-chain Pool.

Native layout from public Meteora cp-amm Pool/PoolFeesStruct:
discriminator 8, 40-byte BaseFeeStruct, 8-byte protocol/partner/referral
metadata, 96-byte DynamicFeeStruct, 16-byte padding, token A at byte 168.
This is the actual source pool fee scheduler, not a guessed fee rate.
"""
import base64
from arb.meteora_damm_v2 import PROGRAM,SIZE,DISC,decode
from arb.source_snapshot_manifest import verify
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

# Source fee field decoding only; exact swap pricing lives exclusively in Meteora Rust SDK.
FEE_DENOMINATOR=1_000_000_000
def encode_collection_mode(value):
    if type(value)is not int or value not in (0,1,2):
        raise ValueError("invalid authenticated DAMM collection mode")
    return ("BASE_AND_QUOTE","QUOTE_ONLY","QUOTE_COMPOUNDING")[value]

def time_scheduler_numerator(*,cliff_fee_numerator,number_of_periods,period_frequency,
                             reduction_factor,elapsed,mode):
    if (any(type(v)is not int for v in (cliff_fee_numerator,number_of_periods,
            period_frequency,reduction_factor,elapsed)) or
            cliff_fee_numerator<0 or not 0<=number_of_periods<=1000 or
            period_frequency<=0 or not 0<=reduction_factor<=FEE_DENOMINATOR or
            elapsed<0 or mode not in ("linear","exponential")):
        raise ValueError("invalid source DAMM fee scheduler")
    completed=min(number_of_periods,elapsed//period_frequency)
    if mode=="linear":
        rate=max(0,cliff_fee_numerator-completed*reduction_factor)
    else:
        rate=cliff_fee_numerator
        for _ in range(completed):
            rate=rate*(FEE_DENOMINATOR-reduction_factor)//FEE_DENOMINATOR
    return {"fee_numerator":rate,"periods_elapsed":completed,
            "fee_precision":FEE_DENOMINATOR,"scheduler_input_authenticated":False,
            "dynamic_fee_included":False,**SAFE}

def source_volatility_fee_candidate(*,volatility_accumulator,bin_step,
                                    variable_fee_control,max_volatility_accumulator):
    values=(volatility_accumulator,bin_step,variable_fee_control,max_volatility_accumulator)
    if (any(type(v)is not int for v in values) or volatility_accumulator<0
            or bin_step<=0 or variable_fee_control<0 or max_volatility_accumulator<=0):
        raise ValueError("invalid DAMM source volatility configuration")
    capped=min(volatility_accumulator,max_volatility_accumulator)
    numerator=(capped*bin_step)**2*variable_fee_control
    rate=(numerator+100_000_000_000-1)//100_000_000_000
    if rate>990_000_000:raise ValueError("DAMM source volatility exceeds fee ceiling")
    return {"snapshot_dynamic_fee_numerator":rate,
            "volatility_accumulator":volatility_accumulator,
            "effective_capped_accumulator":capped,
            "volatility_limit_applied":capped!=volatility_accumulator,
            "bin_step":bin_step,
            "dynamic_fee_source":"CAPTURED_VOLATILITY_POLYNOMIAL_NO_SWAP_UPDATE",
            "snapshot_dynamic_fee_not_execution_verified":True,
            "protocol_exact_verified":False,**SAFE}

def decode_fee_state(raw):
    if type(raw)is not bytes or len(raw)!=SIZE or raw[:8]!=DISC:
        raise ValueError("DAMM v2 on-chain Pool fee bytes invalid")
    u=lambda a,b:int.from_bytes(raw[a:b],"little")
    base={"cliff_fee_numerator":u(8,16),
          "fee_scheduler_mode":raw[16],
          "number_of_periods":u(22,24),
          "period_frequency":u(24,32),
          "reduction_factor":u(32,40)}
    dynamic={"initialized":raw[56],
             "max_volatility_accumulator":u(64,68),
             "variable_fee_control":u(68,72),
             "bin_step":u(72,74),
             "filter_period":u(74,76),
             "decay_period":u(76,78),
             "reduction_factor":u(78,80),
             "last_update_timestamp":u(80,88),
             "bin_step_u128":u(88,104),
             "sqrt_price_reference_q64":u(104,120),
             "volatility_accumulator":u(120,136),
             "volatility_reference":u(136,152)}
    if (base["fee_scheduler_mode"] not in (0,1) or
            base["cliff_fee_numerator"]>FEE_DENOMINATOR or
            base["number_of_periods"]>1000 or
            (base["number_of_periods"] and base["period_frequency"]==0) or
            dynamic["initialized"] not in (0,1) or
            raw[484] not in (0,1,2)):
        raise ValueError("DAMM v2 native fee mode or scheduler malformed")
    if any(raw[i]>100 for i in (48,49,50)):
        raise ValueError("DAMM fee sharing percentages invalid")
    if dynamic["initialized"] and (
            dynamic["max_volatility_accumulator"]==0 or
            dynamic["bin_step"]==0 or
            dynamic["filter_period"]>dynamic["decay_period"] or
            dynamic["reduction_factor"]>10000):
        raise ValueError("DAMM dynamic fee configuration invalid")
    return {"base_fee":base,"dynamic_fee":dynamic,
            "protocol_fee_percent":raw[48],
            "partner_fee_percent":raw[49],
            "referral_fee_percent":raw[50],
            "native_collection_mode":encode_collection_mode(raw[484]),
            "pool_type":raw[485],
            "pool_status":raw[481],
            "activation_point":u(472,480),
            "activation_type":raw[480],
            "fee_denominator":FEE_DENOMINATOR,
            "fee_source_layout_verified":True,**SAFE}

def effective_base_fee_from_pool(raw,*,source_slot,observed_unix):
    if (type(source_slot)is not int or source_slot<0 or
            type(observed_unix)is not int or observed_unix<0):
        raise ValueError("DAMM base fee requires current source slot and time")
    state=decode_fee_state(raw)
    decoded=decode(raw)
    if decoded["pool_status"]!=0:
        raise ValueError("DAMM source pool is disabled")
    activation=state["activation_point"]
    if state["activation_type"]==0:
        elapsed=source_slot-activation
        clock="source_slot"
    elif state["activation_type"]==1:
        elapsed=observed_unix-activation
        clock="observed_unix"
    else:
        raise ValueError("unsupported DAMM fee scheduler activation clock")
    if elapsed<0:
        raise ValueError("DAMM fee scheduler pool activation is in the future")
    base=state["base_fee"]
    if base["number_of_periods"]==0:
        computed=base["cliff_fee_numerator"]
        periods=0
    else:
        mode="linear" if base["fee_scheduler_mode"]==0 else "exponential"
        schedule=time_scheduler_numerator(
            cliff_fee_numerator=base["cliff_fee_numerator"],
            number_of_periods=base["number_of_periods"],
            period_frequency=base["period_frequency"],
            reduction_factor=base["reduction_factor"],
            elapsed=elapsed,mode=mode)
        computed=schedule["fee_numerator"]
        periods=schedule["periods_elapsed"]
    dynamic_model=None
    if state["dynamic_fee"]["initialized"]:
        d=state["dynamic_fee"]
        dynamic_model=source_volatility_fee_candidate(
            volatility_accumulator=d["volatility_accumulator"],
            bin_step=d["bin_step"],
            variable_fee_control=d["variable_fee_control"],
            max_volatility_accumulator=d["max_volatility_accumulator"])
    return {"source_snapshot_dynamic_fee_model":dynamic_model,
            "source_snapshot_total_fee_candidate":(
                computed+dynamic_model["snapshot_dynamic_fee_numerator"]
                if dynamic_model is not None else computed),
            "base_fee_numerator":computed,
            "base_fee_periods_elapsed":periods,
            "activation_clock":clock,"activation_elapsed":elapsed,
            "dynamic_fee_initialized":bool(state["dynamic_fee"]["initialized"]),
            "native_collection_mode":state["native_collection_mode"],
            "protocol_exact_total_fee_verified":False,
            "source_native_fee_fields":state,**SAFE}

def from_fixture(fixture,*,pool,observed_unix):
    verify(fixture)
    if any(fixture.get(key)is not False for key in SAFE):
        raise ValueError("unsafe DAMM pool source fee fixture")
    if pool not in fixture["state_account_addresses"]:
        raise ValueError("source DAMM fee pool missing from single-slot manifest")
    account=fixture["accounts"].get(pool)
    if (not isinstance(account,dict) or account.get("owner")!=PROGRAM or
            account.get("executable") is not False):
        raise ValueError("source DAMM fee program owner mismatch")
    value=account.get("data")
    if not isinstance(value,list) or len(value)!=2 or value[1]!="base64":
        raise ValueError("source DAMM fee bytes absent")
    raw=base64.b64decode(value[0],validate=True)
    result=effective_base_fee_from_pool(raw,
        source_slot=fixture["state_accounts_observed_slot"],
        observed_unix=observed_unix)
    return {"pool":pool,"source_slot":fixture["state_accounts_observed_slot"],
            **result,**SAFE}
