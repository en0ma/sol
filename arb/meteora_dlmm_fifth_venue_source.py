"""Fifth-venue Meteora DLMM read-only native source capture.

Reuse the existing registry hints, LbPair decoder, SPL vault authentication
and DLMM bin-array PDA logic. This deliberately does not invent a quote from
aggregate reserves: DLMM requires per-bin liquidity, variable fees and Clock.
No signing, native parity, registry promotion or broadcasting.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
from solders.pubkey import Pubkey
from arb.rpc import call
from arb.meteora_dlmm import PROGRAM, decode
from arb.meteora_dlmm_bin_preflight import (
    active_bin_array_index,bin_array_pda,BIN_ARRAY_DISC,ORACLE_DISC)
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account

CLOCK="SysvarC1ock11111111111111111111111111111111"
SYSVAR="Sysvar1111111111111111111111111111111111111"

SAFE={"actionable":False,"broadcast":False,"signed_parity_verified":False,
      "native_pricing_verified":False,"registry_admission_approved":False}


def _raw(account,owner,*,optional=False):
    if account is None and optional:
        return None
    if (not isinstance(account,dict) or account.get("owner")!=owner
            or account.get("executable") is not False):
        raise ValueError("DLMM source account owner/flag mismatch")
    data=account.get("data")
    if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
        raise ValueError("DLMM source base64 missing")
    raw=base64.b64decode(data[0],validate=True)
    if not raw or base64.b64encode(raw).decode()!=data[0]:
        raise ValueError("DLMM noncanonical source bytes")
    return raw


def capture_pool(rpc,address,expected_mints):
    first=call(rpc,"getAccountInfo",[address,{
        "encoding":"base64","commitment":"confirmed"}])
    initial=_raw(first.get("value"),PROGRAM)
    state=decode(initial)
    mints=[state["token_x_mint"],state["token_y_mint"]]
    if (expected_mints is not None and (
            not isinstance(expected_mints,list) or len(expected_mints)!=2
            or set(mints)!=set(expected_mints))):
        raise ValueError("DLMM registry mint identity mismatch")
    if (state["status"]!=0 or state["token_mint_x_program_flag"]!=0
            or state["token_mint_y_program_flag"]!=0):
        raise ValueError("DLMM disabled or unsupported token extensions")
    idx=active_bin_array_index(state["active_id"])
    # Three SDK arrays in each direction may skip uninitialized arrays.
    # Capture a bounded 17-array neighborhood, all at the same source slot.
    array_indexes=list(range(idx-8,idx+9))
    arrays=[bin_array_pda(address,i) for i in array_indexes]
    extension=str(Pubkey.find_program_address(
        [b"bitmap",bytes(Pubkey.from_string(address))],Pubkey.from_string(PROGRAM))[0])
    keys=[address,state["reserve_x"],state["reserve_y"],state["oracle"],
          *arrays,*mints,CLOCK,extension]
    result=call(rpc,"getMultipleAccounts",[
        keys,{"encoding":"base64","commitment":"confirmed"}])
    slot=result.get("context",{}).get("slot")
    accounts=result.get("value")
    if type(slot) is not int or slot<0 or not isinstance(accounts,list) or len(accounts)!=len(keys):
        raise ValueError("DLMM complete same-slot source snapshot missing")
    synchronized=decode(_raw(accounts[0],PROGRAM))
    # A DLMM pool's active price/fee state is mutable. The initial read
    # discovers address roles, but ONLY the second, synchronized
    # getMultipleAccounts state is priced. Permit price/fee changes when
    # ALL account-role PDAs and the active-array index remain identical.
    if (any(synchronized[k]!=state[k] for k in (
            "reserve_x","reserve_y","token_x_mint","token_y_mint",
            "oracle","bin_step")) or
            active_bin_array_index(synchronized["active_id"])!=idx):
        raise ValueError("DLMM pool account roles or active array changed during capture")
    if (synchronized["status"]!=0 or
            synchronized["token_mint_x_program_flag"]!=0 or
            synchronized["token_mint_y_program_flag"]!=0):
        raise ValueError("DLMM synchronized pool disabled or unsupported")
    state=synchronized
    reserves=[decode_token_account(_raw(accounts[i],TOKEN_PROGRAM)) for i in (1,2)]
    if ([r["mint"] for r in reserves]!=mints or
            reserves[0]["authority"]!=reserves[1]["authority"] or
            min(r["amount_base_units"] for r in reserves)<=0):
        raise ValueError("DLMM vault mint, authority or liquidity invalid")
    oracle=_raw(accounts[3],PROGRAM)
    if len(oracle)<32 or oracle[:8]!=ORACLE_DISC:
        raise ValueError("DLMM price oracle invalid")
    observation_index=int.from_bytes(oracle[8:16],"little")
    observation_count=int.from_bytes(oracle[16:24],"little")
    observation_capacity=int.from_bytes(oracle[24:32],"little")
    if (not observation_capacity or observation_count>observation_capacity
            or observation_index>=observation_capacity):
        raise ValueError("DLMM oracle observation header invalid")
    verified_bins=[]
    for index,pda,account in zip(array_indexes,arrays,accounts[4:4+len(arrays)]):
        data=_raw(account,PROGRAM,optional=index!=idx)
        if data is None:
            verified_bins.append({"index":index,"pda":pda,"authenticated":False})
            continue
        if (len(data)<56 or data[:8]!=BIN_ARRAY_DISC or
                int.from_bytes(data[8:16],"little",signed=True)!=index or
                data[16] not in (0,1,2) or
                str(Pubkey.from_bytes(data[24:56]))!=address):
            raise ValueError("DLMM indexed bin array parent/owner mismatch")
        verified_bins.append({"index":index,"pda":pda,"authenticated":True})
    if not any(b["index"]==idx and b["authenticated"] for b in verified_bins):
        raise ValueError("DLMM active bin liquidity source unavailable")
    mint_offset=4+len(arrays)
    for account in accounts[mint_offset:mint_offset+2]:
        mint_bytes=_raw(account,TOKEN_PROGRAM)
        if len(mint_bytes)!=82 or mint_bytes[45]!=1:
            raise ValueError("DLMM classic mint uninitialized")
    clock=_raw(accounts[mint_offset+2],SYSVAR)
    if len(clock)!=40:
        raise ValueError("DLMM synchronized Clock sysvar length invalid")
    clock_slot=int.from_bytes(clock[0:8],"little")
    clock_timestamp=int.from_bytes(clock[32:40],"little",signed=True)
    if clock_slot<slot-1024 or clock_timestamp<=0:
        raise ValueError("DLMM Clock not compatible with synchronized snapshot")
    extension_account=accounts[mint_offset+3]
    if extension_account is not None:
        extension_raw=_raw(extension_account,PROGRAM)
        if (len(extension_raw)<40 or
                extension_raw[:8]!=hashlib.sha256(b"account:BinArrayBitmapExtension").digest()[:8] or
                extension_raw[8:40]!=bytes(Pubkey.from_string(address))):
            raise ValueError("DLMM authenticated bitmap extension owner, discriminator or pool invalid")
    records=[{"address":key,"owner":account["owner"],
              "lamports":account["lamports"],"account_base64":account["data"][0]}
             if account is not None else {"address":key,"present":False}
             for key,account in zip(keys,accounts)]
    digest=hashlib.sha256(json.dumps({
        "slot":slot,"accounts":records},sort_keys=True,
        separators=(",",":")).encode()).hexdigest()
    return {"venue":"meteora_dlmm","address":address,
            "status":"AUTHENTICATED_BIN_SNAPSHOT_ONLY",
            "mints":mints,"source_slot":slot,"active_id":state["active_id"],
            "bin_step":state["bin_step"],"bin_arrays":verified_bins,
            "fork_clock_slot":clock_slot,"fork_clock_unix_timestamp":clock_timestamp,
            "source_accounts":records,"source_sha256":digest,
            "signed_sdk_native_parity_verified":False,**SAFE}


def capture(rpc,registry,*,count=3,unverified_only=False):
    if (type(count) is not int or not 1<=count<=6
            or not isinstance(registry,dict)
            or not isinstance(registry.get("pools"),list)):
        raise ValueError("invalid bounded fifth-venue source request")
    candidates=[row for row in registry["pools"] if isinstance(row,dict)
                and row.get("venue")=="meteora_dlmm"
                and (not unverified_only or not row.get("signed_provenance"))]
    results=[];rejected=[];seen=set()
    for row in candidates:
        address=row.get("address")
        if not isinstance(address,str) or address in seen:
            continue
        seen.add(address)
        try:
            results.append(capture_pool(rpc,address,row.get("mints")))
        except (ValueError,TypeError,KeyError,RuntimeError,OSError) as exc:
            rejected.append({"address":address,"reason":str(exc)[:200]})
        if len(results)==count:break
    return {"venue":"meteora_dlmm","status":"FIFTH_VENUE_SOURCE_RESEARCH",
            "requested":count,"authenticated":len(results),"pools":results,
            "rejected":rejected,**SAFE}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rpc",required=True)
    p.add_argument("--registry",default="arb/pool_registry.json")
    p.add_argument("--count",type=int,default=3)
    p.add_argument("--output",required=True)
    p.add_argument("--unverified-only",action="store_true")
    args=p.parse_args()
    result=capture(args.rpc,json.loads(Path(args.registry).read_text()),
                   count=args.count,unverified_only=args.unverified_only)
    Path(args.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"venue":result["venue"],"authenticated":result["authenticated"],
                      "requested":result["requested"],"status":result["status"]}))
    if result["authenticated"]!=result["requested"]:
        raise SystemExit("DLMM fifth-venue authenticated source target incomplete")


if __name__=="__main__":
    main()
