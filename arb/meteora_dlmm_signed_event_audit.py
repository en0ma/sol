"""Independent DLMM Swap event reconciliation against signed route identity.

Pinned Meteora DLMM SDK IDL Swap event layout, 2026-11 source revision
1532e540db41ac405dbf4c5bb2ddfceaa1f98ff1. Event data is recorded RPC
evidence; it is not a cryptographically attested execution response.
"""
import struct
from arb.damm_cpmm_atomic_offline import _decode_base58
from arb.meteora_dlmm import PROGRAM
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
EVENT_TAG=bytes.fromhex("e445a52e51cb9a1d516ce3becdd00ac4")

def decode_swap(raw):
    from solders.pubkey import Pubkey
    if not isinstance(raw,bytes) or len(raw)!=145 or raw[:16]!=EVENT_TAG:
        raise ValueError("unsupported DLMM Swap event layout")
    a,b,amount_in,amount_out,direction,fee,protocol=struct.unpack_from("<iiQQBQQ",raw,80)
    if direction not in (0,1) or not amount_in or not amount_out or protocol>fee:
        raise ValueError("invalid DLMM Swap event fields")
    return {"pool":str(Pubkey.from_bytes(raw[16:48])),"authority":str(Pubkey.from_bytes(raw[48:80])),
            "start_bin_id":a,"end_bin_id":b,"amount_in":amount_in,"amount_out":amount_out,
            "swap_for_y":bool(direction),"fee":fee,"protocol_fee":protocol,
            "reported_fee_bps_raw":int.from_bytes(raw[121:137],"little"),
            "host_fee":int.from_bytes(raw[137:145],"little")}

def audit_swap_event(response,keys,ix,pool,payer,leg_index,amount_in,amount_out):
    from solders.pubkey import Pubkey
    keys=[str(k) for k in keys]
    if keys[ix.program_id_index]!=PROGRAM or pool not in [keys[i] for i in ix.accounts]:
        raise ValueError("DLMM event signed instruction mismatch")
    authority=str(Pubkey.find_program_address([b"__event_authority"],Pubkey.from_string(PROGRAM))[0])
    groups=[g for g in response.get("innerInstructions",[]) if g.get("index")==leg_index]
    if len(groups)!=1:
        raise ValueError("DLMM event CPI group unavailable")
    events=[]
    for entry in groups[0]["instructions"]:
        if entry.get("programId")!=PROGRAM or not isinstance(entry.get("data"),str):
            continue
        raw=_decode_base58(entry["data"])
        if raw[:16]==EVENT_TAG:
            if entry.get("accounts")!=[authority]:
                raise ValueError("DLMM event authority mismatch")
            events.append(decode_swap(raw))
    if not events:
        return {"status":"DLMM_SWAP_EVENT_NOT_PRESENT","protocol_exact_verified":False,**SAFE}
    if len(events)!=1:
        raise ValueError("ambiguous DLMM Swap event")
    e=events[0]
    if (e["pool"],e["authority"],e["amount_in"],e["amount_out"])!=(pool,payer,amount_in,amount_out):
        raise ValueError("DLMM event amount or identity mismatch")
    return {"status":"DLMM_RECORDED_SWAP_EVENT_RECONCILED","event":e,
            "protocol_exact_verified":False,**SAFE}

def stable_execution_timestamp(evidence):
    a=evidence.get("positive_execution_clock_before")
    b=evidence.get("positive_execution_clock_after")
    for c in (a,b):
        if (not isinstance(c,dict) or type(c.get("slot")) is not int or c["slot"]<0
                or type(c.get("unix_timestamp")) is not int or c["unix_timestamp"]<0):
            return None
    if b["slot"]<a["slot"] or a["unix_timestamp"]!=b["unix_timestamp"]:
        return None
    return a["unix_timestamp"]
