"""Native DAMM v2 u1e9 fee arithmetic and deterministic scheduler primitives.

Meteora's cp-amm fee denominator is 1_000_000_000 (not 1e6).
This module performs integer exact-input fee rounding against the currently
observed source token reserves. An effective swap quote still requires the
pool's authenticated base/dynamic fee configuration and curve bounds.
"""
FEE_DENOMINATOR=1_000_000_000
MAX_FEE_V0=500_000_000
MAX_FEE_V1=990_000_000
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def ceil_div(n,d):
    if type(n)is not int or type(d)is not int or n<0 or d<=0:
        raise ValueError("nonnegative integer division required")
    return (n+d-1)//d

def encode_collection_mode(raw):
    if type(raw)is not int or raw not in (0,1,2):
        raise ValueError("invalid authenticated DAMM collection mode")
    return ("BASE_AND_QUOTE","QUOTE_ONLY","QUOTE_COMPOUNDING")[raw]

def quote_native_fee(*,reserve_a,reserve_b,amount_in,input_is_a,
                     total_fee_numerator,collection_mode,fee_version):
    vals=(reserve_a,reserve_b,amount_in,total_fee_numerator,fee_version)
    if any(type(v)is not int for v in vals) or type(input_is_a)is not bool:
        raise ValueError("DAMM quote requires native integers")
    if min(reserve_a,reserve_b,amount_in)<=0 or amount_in>=2**64:
        raise ValueError("DAMM source reserves or amount invalid")
    ceiling={0:MAX_FEE_V0,1:MAX_FEE_V1}.get(fee_version)
    if ceiling is None or not 0<=total_fee_numerator<=ceiling:
        raise ValueError("DAMM native fee above pool-version ceiling")
    if collection_mode not in ("BASE_AND_QUOTE","QUOTE_ONLY","QUOTE_COMPOUNDING"):
        raise ValueError("DAMM collection mode unverified")
    fee_on_output=(collection_mode=="BASE_AND_QUOTE" or
                   (collection_mode!="BASE_AND_QUOTE" and input_is_a))
    reserve_in,reserve_out=(reserve_a,reserve_b) if input_is_a else (reserve_b,reserve_a)
    input_fee=0 if fee_on_output else ceil_div(amount_in*total_fee_numerator,FEE_DENOMINATOR)
    used=amount_in-input_fee
    if used<=0:raise ValueError("DAMM input exhausted by native fees")
    gross_out=reserve_out*used//(reserve_in+used)
    output_fee=ceil_div(gross_out*total_fee_numerator,FEE_DENOMINATOR) if fee_on_output else 0
    amount_out=gross_out-output_fee
    if not 0<amount_out<reserve_out:
        raise ValueError("DAMM native fee quote cannot fill")
    return {"amount_out":amount_out,"gross_curve_output":gross_out,
            "fee_input_units":input_fee,"fee_output_units":output_fee,
            "fee_denominator":FEE_DENOMINATOR,
            "collection_mode":collection_mode,
            "fee_version":fee_version,
            "pool_fee_configuration_verified":False,
            "curve_range_crossing_verified":False,
            "protocol_exact_verified":False,**SAFE}

def time_scheduler_numerator(*,cliff_fee_numerator,number_of_periods,
                             period_frequency,reduction_factor,
                             elapsed,mode):
    """Deterministic integer reductions; caller must authenticate scheduler bytes.

    For each completed period the linear mode reduces the original cliff
    numerator by a fixed amount, while exponential mode reduces the running
    fee. No market-cap scheduler, rate-limiter or dynamic fee is inferred.
    """
    params=(cliff_fee_numerator,number_of_periods,period_frequency,
            reduction_factor,elapsed)
    if (any(type(x)is not int for x in params) or
            cliff_fee_numerator<0 or not 0<=number_of_periods<=1000 or
            period_frequency<=0 or not 0<=reduction_factor<=FEE_DENOMINATOR or
            elapsed<0 or mode not in ("linear","exponential")):
        raise ValueError("invalid source DAMM fee scheduler inputs")
    completed=min(number_of_periods,elapsed//period_frequency)
    if mode=="linear":
        rate=max(0,cliff_fee_numerator-completed*reduction_factor)
    else:
        rate=cliff_fee_numerator
        for _ in range(completed):
            rate=rate*(FEE_DENOMINATOR-reduction_factor)//FEE_DENOMINATOR
    return {"fee_numerator":rate,"periods_elapsed":completed,
            "fee_precision":FEE_DENOMINATOR,
            "scheduler_input_authenticated":False,
            "dynamic_fee_included":False,**SAFE}

def source_volatility_fee_candidate(*, volatility_accumulator, bin_step,
                                    variable_fee_control, max_volatility_accumulator):
    """Compute the published DAMM v2 dynamic-fee integer polynomial.

    The source accumulator is a snapshot input, NOT the post-swap volatility
    accumulator. The caller may compare the result to a signed observation,
    but must not treat this model as protocol-exact execution pricing.
    """
    values=(volatility_accumulator,bin_step,variable_fee_control,
            max_volatility_accumulator)
    if (any(type(v)is not int for v in values) or
            not 0<=volatility_accumulator<=max_volatility_accumulator or
            bin_step<=0 or variable_fee_control<0 or
            max_volatility_accumulator<=0):
        raise ValueError("invalid source DAMM volatility configuration")
    numerator=(volatility_accumulator*bin_step)**2*variable_fee_control
    result=ceil_div(numerator,100_000_000_000)
    if result>MAX_FEE_V1:
        raise ValueError("DAMM volatility fee exceeds native version ceiling")
    return {"snapshot_dynamic_fee_numerator":result,
            "volatility_accumulator":volatility_accumulator,
            "bin_step":bin_step,
            "dynamic_fee_source":"CAPTURED_VOLATILITY_POLYNOMIAL_NO_SWAP_UPDATE",
            "snapshot_dynamic_fee_not_execution_verified":True,
            "protocol_exact_verified":False,**SAFE}
