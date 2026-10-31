"""Read and compare the isolated Surfpool Clock sysvar around an Orca swap.

The snapshot measures the fork's current Unix time, not historical mainnet
state time. It may not be passed off as an authenticated mainnet source slot.
"""
import base64
from arb.rpc import call
CLOCK="SysvarC1ock11111111111111111111111111111111"
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}

def fork_clock(rpc):
    response=call(rpc,"getAccountInfo",
        [CLOCK,{"encoding":"base64","commitment":"confirmed"}])
    if not isinstance(response,dict):
        raise ValueError("fork Clock response malformed")
    value=response.get("value")
    if (not isinstance(value,dict) or
            value.get("owner")!="Sysvar1111111111111111111111111111111111111" or
            value.get("executable") is not False):
        raise ValueError("fork Clock sysvar identity is not verified")
    data=value.get("data")
    if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
        raise ValueError("fork Clock sysvar bytes not captured")
    raw=base64.b64decode(data[0],validate=True)
    if len(raw)!=40:
        raise ValueError("invalid Solana Clock sysvar layout")
    slot=int.from_bytes(raw[0:8],"little")
    epoch_start=int.from_bytes(raw[8:16],"little",signed=True)
    epoch=int.from_bytes(raw[16:24],"little")
    leader_epoch=int.from_bytes(raw[24:32],"little")
    unix=int.from_bytes(raw[32:40],"little",signed=True)
    if not 0<=slot<2**64 or not 0<=epoch<2**64 or not 0<=leader_epoch<2**64 or unix<=0:
        raise ValueError("invalid isolated fork Clock fields")
    return {"fork_clock_slot":slot,"fork_unix_timestamp":unix,
            "fork_epoch_start_unix":epoch_start,"fork_epoch":epoch,
            "fork_leader_schedule_epoch":leader_epoch,
            "clock_source":"ISOLATED_SURFPOOL_CLOCK_SYSVAR",**SAFE}

def stable_orca_fork_clock(before,after):
    for item in (before,after):
        if not isinstance(item,dict) or any(item.get(k)is not False for k in SAFE):
            raise ValueError("safe fork Clock readback required")
        if item.get("clock_source")!="ISOLATED_SURFPOOL_CLOCK_SYSVAR":
            raise ValueError("fork Clock is not an authenticated sysvar readback")
    if before["fork_unix_timestamp"]!=after["fork_unix_timestamp"]:
        return {"status":"ORCA_FORK_CLOCK_CHANGED_DURING_SIGNED_ATTEMPT",
                "fork_unix_timestamp":None,
                "fork_clock_stable_for_quote":False,**SAFE}
    return {"status":"ORCA_FORK_CLOCK_STABLE_FOR_SIGNED_ATTEMPT",
            "fork_unix_timestamp":before["fork_unix_timestamp"],
            "fork_clock_before":before,"fork_clock_after":after,
            "fork_clock_stable_for_quote":True,**SAFE}
