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
