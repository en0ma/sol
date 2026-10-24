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

def inspect(rpc,pool,zero_for_one=True,arrays=3):
    if type(zero_for_one)is not bool or type(arrays)is not int or not 1<=arrays<=5:
        raise ValueError("invalid preflight options")
    result=call(rpc,"getAccountInfo",[pool,{"encoding":"base64","commitment":"confirmed"}]).get("value")
    if not result or result.get("owner")!=PROGRAM:raise ValueError("missing CLMM pool")
    state=decode(base64.b64decode(result["data"][0],validate=True))
    first=start_tick(state["tick_current"],state["tick_spacing"])
    step=60*state["tick_spacing"]*(-1 if zero_for_one else 1)
    starts=[first+i*step for i in range(arrays)]
    addresses=[tick_array_pda(pool,s) for s in starts]
    values=call(rpc,"getMultipleAccounts",[addresses,{"encoding":"base64",
                                                      "commitment":"confirmed"}]).get("value")
    if not isinstance(values,list) or len(values)!=arrays:raise ValueError("missing tick array response")
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
