"""Decode DLMM LbPair static fee configuration from actual 904-byte account.

Source layout: 8-byte Anchor discriminator, 32-byte StaticParameters,
32-byte VariableParameters. Base fee is exact static numerator in 1e9
precision; dynamic rate requires a fresh volatility reference update, so this
module never substitutes the base rate for an effective swap fee.
"""
import base64
from arb.meteora_dlmm import PROGRAM,SIZE,DISC
from arb.source_snapshot_manifest import verify

FEE_PRECISION=1_000_000_000
MAX_FEE_NUMERATOR=100_000_000
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def static_parameters(raw):
    if type(raw)is not bytes or len(raw)!=SIZE or raw[:8]!=DISC:
        raise ValueError("invalid DLMM LbPair bytes for native fee decoder")
    b=raw[8:40]
    u=lambda offset,size:int.from_bytes(b[offset:offset+size],"little")
    result={"base_factor":u(0,2),"filter_period":u(2,2),
        "decay_period":u(4,2),"reduction_factor":u(6,2),
        "variable_fee_control":u(8,4),
        "max_volatility_accumulator":u(12,4),
        "min_bin_id":int.from_bytes(b[16:20],"little",signed=True),
        "max_bin_id":int.from_bytes(b[20:24],"little",signed=True),
        "protocol_share":u(24,2),
        "base_fee_power_factor":u(26,1),
        "function_type":u(27,1),
        "collect_fee_mode":u(28,1)}
    if result["min_bin_id"]>result["max_bin_id"]:
        raise ValueError("DLMM native bin range malformed")
    if not 0<=result["reduction_factor"]<=10000:
        raise ValueError("DLMM native fee reduction factor malformed")
    return result

def limit_order_supported(raw):
    """Pinned SDK LbPair::is_support_limit_order, with strict layout checks.

    FunctionType 0 derives the mode from the two reward mint keys;
    1 is liquidity mining; 2 is limit orders. Never interpret a missing
    field, short reward inventory or unsupported discriminant as MM-only.
    """
    kind=static_parameters(raw)["function_type"]
    if kind==1:
        return False
    if kind==2:
        return True
    if kind==0:
        return raw[264:296]==bytes(32) and raw[408:440]==bytes(32)
    raise ValueError("unsupported DLMM function type")


def variable_parameters(raw):
    if type(raw)is not bytes or len(raw)!=SIZE or raw[:8]!=DISC:
        raise ValueError("invalid DLMM LbPair bytes for volatility decoder")
    b=raw[40:72]
    u=lambda offset,size:int.from_bytes(b[offset:offset+size],"little")
    return {"volatility_accumulator":u(0,4),
            "volatility_reference":u(4,4),
            "index_reference":int.from_bytes(b[8:12],"little",signed=True),
            "last_update_timestamp":int.from_bytes(b[16:24],"little",signed=True)}

def source_fee_bounds(raw, *, bin_step, observed_unix):
    if type(bin_step)is not int or not 0<bin_step<10000:
        raise ValueError("verified DLMM bin step required")
    if type(observed_unix)is not int or observed_unix<0:
        raise ValueError("native DLMM observation timestamp required")
    static=static_parameters(raw)
    volatile=variable_parameters(raw)
    # From DLMM StaticParameters: base_factor * bin_step * 10 *
    # 10**base_fee_power_factor, numerator over 1e9.
    exponent=static["base_fee_power_factor"]
    if exponent>9:
        raise ValueError("DLMM base fee exponent exceeds supported bounds")
    base=static["base_factor"]*bin_step*10*10**exponent
    if base>MAX_FEE_NUMERATOR:
        raise ValueError("DLMM static fee exceeds 10% protocol ceiling")
    if volatile["volatility_accumulator"]>static["max_volatility_accumulator"]:
        raise ValueError("DLMM observed volatility exceeds configured maximum")
    # Bound total by protocol max. Volatility reference must be evolved
    # with the fresh observation clock before precise fee is possible.
    return {"static":static,"variable":volatile,
        "base_fee_rate_numerator":base,
        "minimum_total_fee_rate_numerator":base,
        "maximum_total_fee_rate_numerator":MAX_FEE_NUMERATOR,
        "fee_precision":FEE_PRECISION,
        "dynamic_fee_verified":False,
        "protocol_exact_verified":False,
        "observed_unix":observed_unix,**SAFE}

def fee_bounds_from_fixture(fixture, *, pool, observed_unix):
    from arb.meteora_dlmm import decode
    verify(fixture)
    if any(fixture.get(k)is not False for k in SAFE):
        raise ValueError("unsafe DLMM fixture for native fee decoding")
    if pool not in fixture["state_account_addresses"]:
        raise ValueError("DLMM pool absent from contextual inventory")
    account=fixture["accounts"][pool]
    encoded=account.get("data")
    if account.get("owner")!=PROGRAM or account.get("executable") is not False:
        raise ValueError("DLMM native pool owner mismatch")
    if not isinstance(encoded,list) or len(encoded)!=2 or encoded[1]!="base64":
        raise ValueError("DLMM pool source bytes missing")
    raw=base64.b64decode(encoded[0],validate=True)
    state=decode(raw)
    return {**source_fee_bounds(raw,bin_step=state["bin_step"],
                  observed_unix=observed_unix),
            "pool":pool,"source_slot":fixture["state_accounts_observed_slot"],**SAFE}

def dynamic_fee_rate_by_bin(raw, *, bin_step, observed_unix, active_bin_id,
                            visited_bin_ids, swap_x_for_y, allow_output_fee=False,
                            verified_empty_arrays=()):
    """Reproduce integer volatility references and bin-crossing fee numerators.

    Based on Meteora DLMM LbPair update_references,
    update_volatility_accumulator and compute_variable_fee. This prices the
    observed local slot and explicit swap direction only. Swap fee collection
    mode and SPL token transfer extensions remain separately gated.
    """
    if (type(active_bin_id)is not int or type(swap_x_for_y)is not bool
            or not isinstance(visited_bin_ids,list) or not 1<=len(visited_bin_ids)<=560
            or visited_bin_ids[0]!=active_bin_id
            or any(type(i)is not int for i in visited_bin_ids)
            or not isinstance(verified_empty_arrays,(tuple,list))
            or len(verified_empty_arrays)>7
            or any(type(i) is not int for i in verified_empty_arrays)
            or len(set(verified_empty_arrays))!=len(verified_empty_arrays)):
        raise ValueError("invalid contiguous DLMM source bin traversal")
    step=-1 if swap_x_for_y else 1
    for previous,current in zip(visited_bin_ids,visited_bin_ids[1:]):
        distance=(current-previous)*step
        if distance==1:
            continue
        if (not 1<distance<=491 or previous%70!=(0 if swap_x_for_y else 69)
                or current%70!=(69 if swap_x_for_y else 0)
                or any(i not in verified_empty_arrays for i in
                       range(previous//70+step,current//70,step))):
            raise ValueError("invalid contiguous DLMM source bin traversal")
    state=source_fee_bounds(raw,bin_step=bin_step,observed_unix=observed_unix)
    static=state["static"];variable=state["variable"]
    mode=static["collect_fee_mode"]
    if mode not in (0,1):
        raise ValueError("unsupported native DLMM fee collection mode")
    if type(allow_output_fee) is not bool:
        raise ValueError("explicit DLMM output fee support required")
    fee_on_input=(mode==0 or not swap_x_for_y)
    if not fee_on_input and not allow_output_fee:
        raise ValueError("DLMM Y-only output-denominated fee requires separate pricing")
    elapsed=observed_unix-variable["last_update_timestamp"]
    if elapsed<0:
        raise ValueError("DLMM quote observation precedes source pool volatility clock")
    if not static["filter_period"]<=static["decay_period"]:
        raise ValueError("DLMM source fee decay windows inconsistent")
    reference=variable["volatility_reference"]
    index=variable["index_reference"]
    if elapsed>=static["filter_period"]:
        index=active_bin_id
        if elapsed<static["decay_period"]:
            reference=(variable["volatility_accumulator"]*static["reduction_factor"])//10000
        else:
            reference=0
    base=state["base_fee_rate_numerator"]
    rates=[]
    for bin_id in visited_bin_ids:
        volatility=min(reference+abs(index-bin_id)*10000,
                       static["max_volatility_accumulator"])
        scaled=volatility*bin_step
        fee_numerator=(static["variable_fee_control"]*scaled*scaled+100_000_000_000-1)//100_000_000_000
        effective=min(base+fee_numerator,MAX_FEE_NUMERATOR)
        rates.append({"bin_id":bin_id,"effective_fee_rate":effective,
                      "volatility_accumulator":volatility,
                      "base_fee_rate":base,"variable_fee_rate":fee_numerator})
    return {"rates":rates,"reference_bin_id":index,
            "updated_volatility_reference":reference,
            "observed_unix":observed_unix,
            "fee_collect_mode":mode,"fee_on_input":fee_on_input,
            "integer_fee_schedule_derived":True,
            "protocol_exact_verified":False,**SAFE}
