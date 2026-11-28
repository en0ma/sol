"""Raydium CLMM tick-array preflight via deterministic PDA and RPC only.

This checks candidate contiguous arrays, not tick bitmap traversal or
execution readiness. Only present, owned, correctly indexed arrays pass.
"""
import argparse,base64,hashlib,json,os
from arb.rpc import call
from arb.raydium_clmm import PROGRAM,decode
from arb.orca_whirlpool import b58
SIZE=10240
DISC=hashlib.sha256(b"account:TickArrayState").digest()[:8]

def start_tick(tick,spacing):
    if type(tick)is not int or type(spacing)is not int or not 1<=spacing<=32767:
        raise ValueError("invalid tick or spacing")
    span=60*spacing
    return tick//span*span

def tick_array_pda(pool,start):
    from solders.pubkey import Pubkey
    if not -(1<<31)<=start<1<<31:raise ValueError("tick start out of range")
    return str(Pubkey.find_program_address(
        [b"tick_array",bytes(Pubkey.from_string(pool)),start.to_bytes(4,"big",signed=True)],
        Pubkey.from_string(PROGRAM))[0])

# PoolState: 904 bytes through reward_infos; then 16 packed u64 bitmap words.
# Offset derived from Raydium CLMM PoolState repr(C,packed) source layout.
POOL_BITMAP_OFFSET=904
POOL_BITMAP_BYTES=128

def initialized_tick_starts(raw, tick, spacing, zero_for_one, *, arrays=3):
    """Choose first and subsequent initialized tick arrays from source PoolState.

    Only the default 1024-bit bitmap is supported here. Extension-dependent
    directions fail closed, never substitute merely existing tick-array PDAs.
    """
    if (not isinstance(raw,(bytes,bytearray)) or len(raw)!=1544
            or type(zero_for_one)is not bool or type(arrays)is not int
            or not 1<=arrays<=5):
        raise ValueError("authenticated CLMM PoolState bytes required")
    first=start_tick(tick,spacing)
    span=60*spacing
    bitmap=int.from_bytes(raw[POOL_BITMAP_OFFSET:POOL_BITMAP_OFFSET+POOL_BITMAP_BYTES],"little")
    offset=first//span+512
    if not 0<=offset<1024:
        raise ValueError("CLMM tick bitmap extension required")
    delta=-1 if zero_for_one else 1
    selected=[]
    for k in range(offset, -1 if zero_for_one else 1024,delta):
        if (bitmap>>k)&1:
            selected.append((k-512)*span)
            if len(selected)>=arrays:
                break
    if not selected:
        raise ValueError("no initialized CLMM tick array in default bitmap direction")
    # A traversal crossing the default bitmap boundary may need an authenticated
    # extension. Do not imply this bounded prefix is the complete swap quote.
    return selected

def bitmap_bit(default_bytes,index,extension_raw=None):
    """Official TickArrayBitmapExtension negative groups use ascending bits."""
    if type(default_bytes) is not bytes or len(default_bytes)!=128 or type(index) is not int:
        raise ValueError("CLMM bitmap bytes or index invalid")
    if -512<=index<512:
        return bool((int.from_bytes(default_bytes,"little")>>(index+512))&1)
    from arb.raydium_clmm_bitmap_extension_source import LENGTH,DISC as EXT_DISC
    if (not isinstance(extension_raw,bytes) or len(extension_raw)!=LENGTH
            or extension_raw[:8]!=EXT_DISC):
        raise ValueError("CLMM tick bitmap extension required for source coverage")
    group=(index//512-1 if index>=512 else (-index-1)//512-1)
    if not 0<=group<14:
        raise ValueError("CLMM tick index outside extension range")
    offset=40+64*group+(0 if index>=512 else 14*64)
    return bool((int.from_bytes(extension_raw[offset:offset+64],"little")>>(index%512))&1)


def extension_bytes(pool,address,account):
    from arb.raydium_clmm_bitmap_extension_source import bitmap_pda,LENGTH,DISC as EXT_DISC
    if (address!=bitmap_pda(pool) or not isinstance(account,dict)
            or account.get("owner")!=PROGRAM or account.get("executable") is not False):
        raise ValueError("CLMM extension PDA or owner mismatch")
    data=account.get("data")
    if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
        raise ValueError("CLMM bitmap extension encoding mismatch")
    raw=base64.b64decode(data[0],validate=True)
    if len(raw)!=LENGTH or raw[:8]!=EXT_DISC or b58(raw[8:40])!=pool:
        raise ValueError("CLMM extension layout or pool mismatch")
    return raw


def extended_tick_starts(raw,extension_raw,tick,spacing,zero_for_one,*,arrays=3):
    if (not isinstance(raw,bytes) or len(raw)!=1544 or type(zero_for_one) is not bool
            or type(arrays) is not int or not 1<=arrays<=5 or not -443636<=tick<=443636):
        raise ValueError("invalid extended CLMM traversal input")
    span=60*spacing
    center=start_tick(tick,spacing)//span
    edge=(-443636//span if zero_for_one else 443636//span)
    step=-1 if zero_for_one else 1
    default=raw[POOL_BITMAP_OFFSET:POOL_BITMAP_OFFSET+POOL_BITMAP_BYTES]
    selected=[]
    for index in range(center,edge+step,step):
        if bitmap_bit(default,index,extension_raw):
            selected.append(index*span)
            if len(selected)==arrays:
                break
    if not selected:
        raise ValueError("no initialized CLMM array in extended direction")
    return selected


def inspect_extended(rpc,pool,zero_for_one,*,arrays=3):
    from arb.raydium_clmm_bitmap_extension_source import bitmap_pda
    address=bitmap_pda(pool)
    result=call(rpc,"getMultipleAccounts",[[pool,address],{"encoding":"base64","commitment":"confirmed"}])
    values=result.get("value")
    if not isinstance(values,list) or len(values)!=2 or not isinstance(values[0],dict):
        raise ValueError("CLMM pool and bitmap source response missing")
    acct=values[0]
    if acct.get("owner")!=PROGRAM or acct.get("executable") is not False:
        raise ValueError("CLMM extended source pool owner mismatch")
    raw=base64.b64decode(acct["data"][0],validate=True);state=decode(raw)
    extension=extension_bytes(pool,address,values[1])
    starts=extended_tick_starts(raw,extension,state["tick_current"],state["tick_spacing"],zero_for_one,arrays=arrays)
    pdas=[tick_array_pda(pool,s) for s in starts]
    response=call(rpc,"getMultipleAccounts",[pdas,{"encoding":"base64","commitment":"confirmed"}])
    vals=response.get("value")
    if not isinstance(vals,list) or len(vals)!=len(pdas):
        raise ValueError("CLMM extended tick source response missing")
    for key,start,value in zip(pdas,starts,vals):
        validate_source_array(pool,key,start,value)
    return {"address":address,"ordered_arrays":pdas,"starts":starts,"zero_for_one":zero_for_one,
        "maximum_arrays":arrays}


def validate_source_array(pool,address,start,value):
    if (address!=tick_array_pda(pool,start) or not isinstance(value,dict)
            or value.get("owner")!=PROGRAM or value.get("executable") is not False):
        raise ValueError("CLMM extended tick array absent or owner mismatch")
    data=value.get("data")
    if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
        raise ValueError("CLMM extended tick array encoding mismatch")
    raw=base64.b64decode(data[0],validate=True)
    if len(raw)!=SIZE or raw[:8]!=DISC or b58(raw[8:40])!=pool or int.from_bytes(raw[40:44],"little",signed=True)!=start:
        raise ValueError("CLMM extended tick array layout mismatch")


def verify_extended_direction(pool,mint_in,aux,fixture):
    """Recompute extension selection from the final contextual original bytes."""
    claim=aux.get("extended_tick_source")
    if claim is None:
        return None
    from arb.source_snapshot_manifest import verify
    verify(fixture)
    accounts=fixture["accounts"];inventory=set(fixture["state_account_addresses"])
    acct=accounts.get(pool)
    if (pool not in inventory or not isinstance(acct,dict) or acct.get("owner")!=PROGRAM
            or acct.get("executable") is not False):
        raise ValueError("CLMM extension source pool absent or owner mismatch")
    data=acct.get("data")
    if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
        raise ValueError("CLMM extension source pool encoding mismatch")
    raw=base64.b64decode(data[0],validate=True);state=decode(raw)
    if mint_in not in (state["token_mint_0"],state["token_mint_1"]):
        raise ValueError("CLMM extended route mint mismatch")
    direction=mint_in==state["token_mint_0"]
    address=claim["address"]
    if address not in inventory:
        raise ValueError("CLMM extension outside source inventory")
    extension=extension_bytes(pool,address,accounts[address])
    starts=extended_tick_starts(raw,extension,state["tick_current"],state["tick_spacing"],direction,arrays=claim["maximum_arrays"])
    pdas=[tick_array_pda(pool,s) for s in starts]
    if (claim["zero_for_one"] is not direction or claim["starts"]!=starts
            or claim["ordered_arrays"]!=pdas or not set(pdas)<=inventory
            or aux["tick_arrays_by_direction"].get("0_to_1" if direction else "1_to_0")!=pdas):
        raise ValueError("CLMM contextual extension traversal changed")
    for key,start in zip(pdas,starts):
        validate_source_array(pool,key,start,accounts[key])
    return address


def inspect(rpc,pool,zero_for_one=True,arrays=3):
    if type(zero_for_one)is not bool or type(arrays)is not int or not 1<=arrays<=5:
        raise ValueError("invalid preflight options")
    result=call(rpc,"getAccountInfo",[pool,{"encoding":"base64","commitment":"confirmed"}]).get("value")
    if not result or result.get("owner")!=PROGRAM:raise ValueError("missing CLMM pool")
    raw_pool=base64.b64decode(result["data"][0],validate=True)
    state=decode(raw_pool)
    starts=initialized_tick_starts(raw_pool,state["tick_current"],
                                    state["tick_spacing"],zero_for_one,arrays=arrays)
    addresses=[tick_array_pda(pool,s) for s in starts]
    values=call(rpc,"getMultipleAccounts",[addresses,{"encoding":"base64",
                                                      "commitment":"confirmed"}]).get("value")
    if not isinstance(values,list) or len(values)!=len(starts):raise ValueError("missing tick array response")
    reports=[]
    for start,address,info in zip(starts,addresses,values):
        valid=False
        if info and info.get("owner")==PROGRAM and not info.get("executable"):
            raw=base64.b64decode(info["data"][0],validate=True)
            valid=(len(raw)==SIZE and raw[:8]==DISC and
                   b58(raw[8:40])==pool and int.from_bytes(raw[40:44],"little",signed=True)==start)
        reports.append({"address":address,"start_tick":start,"validated":valid})
    return {"pool":pool,"direction":"zero_for_one" if zero_for_one else "one_for_zero",
            "tick_arrays":reports,"all_arrays_valid":all(a["validated"] for a in reports),
            "first_initialized_tick_start":starts[0],
            "bitmap_authenticated":True,
            "swap_executed":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--pool",required=True);p.add_argument("--output",default="")
    a=p.parse_args()
    result=inspect(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),a.pool)
    print(json.dumps(result,indent=2))
    if a.output:
        with open(a.output,"w") as f:json.dump(result,f,indent=2)
    return 0 if result["all_arrays_valid"] else 2
if __name__=="__main__":raise SystemExit(main())
