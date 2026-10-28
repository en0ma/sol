"""Source-authenticated Orca adaptive-fee Oracle account decoder.

Oracle is a genuine pricing input when fee_tier_index_seed differs from
tick_spacing. The 254-byte Borsh layout and field offsets are from the
official Orca Whirlpools client. No guessed fee or dummy Oracle is accepted.
"""
import base64
import hashlib
from arb.orca_whirlpool import PROGRAM,b58

ORACLE_SIZE=254
DISC=hashlib.sha256(b"account:Oracle").digest()[:8]
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}

def decode_oracle(raw,pool):
    if (not isinstance(raw,bytes) or len(raw)!=ORACLE_SIZE or raw[:8]!=DISC
            or not isinstance(pool,str) or b58(raw[8:40])!=pool):
        raise ValueError("Orca adaptive fee Oracle layout/pool identity mismatch")
    def le(i,n,*,signed=False):
        return int.from_bytes(raw[i:i+n],"little",signed=signed)
    c={"filter_period":le(48,2),"decay_period":le(50,2),
       "reduction_factor":le(52,2),"adaptive_fee_control_factor":le(54,4),
       "max_volatility_accumulator":le(58,4),"tick_group_size":le(62,2),
       "major_swap_threshold_ticks":le(64,2)}
    v={"last_reference_update_timestamp":le(82,8),
       "last_major_swap_timestamp":le(90,8),
       "volatility_reference":le(98,4),
       "tick_group_index_reference":le(102,4,signed=True),
       "volatility_accumulator":le(106,4)}
    if (c["filter_period"]>c["decay_period"] or
            c["reduction_factor"]>10000 or
            not c["tick_group_size"] or
            not c["max_volatility_accumulator"] or
            v["volatility_reference"]>c["max_volatility_accumulator"] or
            v["volatility_accumulator"]>c["max_volatility_accumulator"]):
        raise ValueError("invalid authenticated Orca adaptive fee constants/variables")
    return {"pool":pool,"trade_enable_timestamp":le(40,8),
            "constants":c,"variables":v,
            "oracle_layout_authenticated":True,
            "effective_adaptive_fee_math_verified":False,**SAFE}

def source_oracle(fixture,pool,state):
    if not isinstance(state,dict) or not isinstance(fixture,dict):
        raise ValueError("authenticated Orca pool source state required")
    if state.get("fee_tier_index_seed")==state.get("tick_spacing"):
        return None
    evidence=fixture.get("leg_evidence_by_index")
    if not isinstance(evidence,list):
        raise ValueError("Orca adaptive fee source Oracle inventory absent")
    matching=[row for row in evidence if isinstance(row,dict) and
              row.get("venue")=="orca" and row.get("pool")==pool]
    if len(matching)!=1:
        raise ValueError("ambiguous Orca source Oracle relationship")
    address=matching[0].get("auxiliary",{}).get("oracle")
    if (not isinstance(address,str) or
            address not in fixture.get("state_account_addresses",[]) or
            fixture["state_account_addresses"].count(address)!=1):
        raise ValueError("Orca adaptive Oracle absent from source inventory")
    info=fixture.get("accounts",{}).get(address)
    if not isinstance(info,dict) or info.get("owner")!=PROGRAM or info.get("executable") is not False:
        raise ValueError("Orca adaptive Oracle owner or executable mismatch")
    data=info.get("data")
    if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
        raise ValueError("Orca adaptive Oracle bytes unavailable")
    return {"oracle_address":address,
            **decode_oracle(base64.b64decode(data[0],validate=True),pool)}
