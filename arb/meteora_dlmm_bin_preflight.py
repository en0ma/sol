"""Read-only Meteora DLMM active-bin array evidence for verified pools.

This preflight is NOT a swap quote or an executable adapter. It verifies the
program-owned active bin array PDA and refuses to infer adjacent liquidity.
No RPC method here may mutate account state.
"""
import base64
import hashlib
from solders.pubkey import Pubkey
from arb.meteora_dlmm import PROGRAM, decode
from arb.rpc import call
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc

BIN_ARRAY_SIZE=70
BIN_ARRAY_DISC=hashlib.sha256(b"account:BinArray").digest()[:8]

def active_bin_array_index(active_id):
    if type(active_id) is not int or not -(1<<31)<=active_id<(1<<31):
        raise ValueError("invalid signed active bin id")
    return active_id//BIN_ARRAY_SIZE

def bin_array_pda(pool, index):
    if type(index) is not int or not -(1<<63)<=index<(1<<63):
        raise ValueError("invalid bin array index")
    program=Pubkey.from_string(PROGRAM)
    pair=Pubkey.from_string(pool)
    return str(Pubkey.find_program_address([
        b"bin_array",bytes(pair),index.to_bytes(8,"little",signed=True)],program)[0])

def inspect_adjacent_bin_arrays(rpc, pool, active_index):
    """Read-only authentication for nearby arrays; presence is not a quote."""
    require_loopback_rpc(rpc)
    if type(active_index) is not int or not -(1<<63)+1 <= active_index < (1<<63)-1:
        raise ValueError("active array index outside safe neighbor range")
    indexes=(active_index-1, active_index, active_index+1)
    addresses=[bin_array_pda(pool,i) for i in indexes]
    response=call(rpc,"getMultipleAccounts",[
        addresses,{"encoding":"base64","commitment":"confirmed"}])
    values=response.get("value")
    if not isinstance(values,list) or len(values)!=3:
        raise ValueError("incomplete neighboring bin array read")
    evidence=[]
    for idx,address,account in zip(indexes,addresses,values):
        row={"index":idx,"pda":address,"present":account is not None}
        if account is None:
            evidence.append(row)
            continue
        if account.get("owner")!=PROGRAM or account.get("executable"):
            raise ValueError("neighboring bin array owner/executable mismatch")
        raw=base64.b64decode(account["data"][0],validate=True)
        if len(raw)<56 or raw[:8]!=BIN_ARRAY_DISC:
            raise ValueError("neighboring bin array discriminator mismatch")
        if int.from_bytes(raw[8:16],"little",signed=True)!=idx or (
            str(Pubkey.from_bytes(raw[24:56]))!=pool):
            raise ValueError("neighboring bin array index/parent mismatch")
        if raw[16] not in (0,1,2):
            raise ValueError("unsupported neighboring array layout version")
        row.update(authenticated=True,byte_length=len(raw))
        evidence.append(row)
    return evidence

def check_active_bin_array(rpc,pool):
    require_loopback_rpc(rpc)
    account=call(rpc,"getAccountInfo",[pool,{"encoding":"base64","commitment":"confirmed"}])["value"]
    if not account or account.get("owner")!=PROGRAM or account.get("executable"):
        raise ValueError("missing genuine Meteora DLMM pair account")
    state=decode(base64.b64decode(account["data"][0],validate=True))
    idx=active_bin_array_index(state["active_id"])
    address=bin_array_pda(pool,idx)
    candidate=call(rpc,"getAccountInfo",[address,{"encoding":"base64","commitment":"confirmed"}])["value"]
    report={"venue":"meteora_dlmm","pool":pool,"active_bin_id":state["active_id"],
            "active_bin_array_index":idx,"active_bin_array_pda":address,
            "swap_instruction_supported":False,"atomic_simulation_verified":False,
            "actionable":False,"broadcast":False}
    if not candidate:
        return dict(report,status="ACTIVE_BIN_ARRAY_ABSENT")
    if candidate.get("owner")!=PROGRAM or candidate.get("executable"):
        raise ValueError("active bin array owner/executable mismatch")
    raw=base64.b64decode(candidate["data"][0],validate=True)
    if len(raw)<56 or raw[:8]!=BIN_ARRAY_DISC:
        raise ValueError("active bin array discriminator/length mismatch")
    actual_index=int.from_bytes(raw[8:16],"little",signed=True)
    if raw[16] not in (0,1,2):
        raise ValueError("unsupported bin array layout version")
    actual_pair=str(Pubkey.from_bytes(raw[24:56]))
    if actual_index!=idx or actual_pair!=pool:
        raise ValueError("active bin array index or parent pool mismatch")
    neighboring=inspect_adjacent_bin_arrays(rpc,pool,idx)
    if neighboring[1].get("authenticated") is not True:
        raise ValueError("active array changed during adjacent read")
    return dict(report,status="ACTIVE_BIN_ARRAY_AUTHENTICATED",
                active_bin_array_byte_length=len(raw),
                neighboring_bin_arrays=neighboring,
                neighboring_arrays_checked=True,
                executable_liquidity_or_quote_verified=False)

def main():
    import json
    import os
    from pathlib import Path
    readiness=json.loads(Path(os.environ["TOKEN_MIXED_READINESS_REPORT"]).read_text())
    target=readiness.get("first_dlmm_only_offline_target")
    report={"status":"NO_VERIFIED_DLMM_TARGET","actionable":False,"broadcast":False,
            "swap_instruction_supported":False}
    if target:
        legs=[leg for leg in target["legs"] if leg["venue"]=="meteora_dlmm"]
        if len(legs)!=1:
            raise ValueError("expected exactly one DLMM leg in selected target")
        report=check_active_bin_array(
            os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),legs[0]["pool"])
        report["target_tokens"]=target["tokens"]
    Path(os.environ["TOKEN_DLMM_BIN_PREFLIGHT_REPORT"]).write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=="__main__":
    main()
