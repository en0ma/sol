"""Read nearby Orca fixed tick-array PDAs from forked Surfpool JSON-RPC.

Missing arrays are reported, not fabricated. Dynamic tick arrays are not
decoded yet. This is prerequisite account inspection, NOT swap execution.
"""
import base64
import hashlib
import json
import os
from arb.rpc import call
from arb.orca_whirlpool import PROGRAM, fetch_pool, b58

ARRAY_TICKS = 88
FIXED_LEN = 9988
DISC = hashlib.sha256(b"account:TickArray").digest()[:8]

def start_tick(index, spacing):
    if spacing <= 0: raise ValueError("invalid spacing")
    span = ARRAY_TICKS * spacing
    return (index // span) * span

def candidate_starts(index, spacing):
    center = start_tick(index, spacing)
    span = spacing * ARRAY_TICKS
    return [center + i * span for i in (0, 1, 2, -1, -2)
            if -443636-span <= center+i*span <= 443636]

def addresses(pool_address, starts):
    from solders.pubkey import Pubkey
    pool = Pubkey.from_string(pool_address)
    program = Pubkey.from_string(PROGRAM)
    return [str(Pubkey.find_program_address(
        [b"tick_array", bytes(pool), str(i).encode()],program)[0]) for i in starts]

def inspect(rpc, pool_address):
    state = fetch_pool(rpc,pool_address)
    spacing=state["tick_spacing"]
    indexes=candidate_starts(state["tick_current_index"],spacing)
    keys=addresses(pool_address,indexes)
    resp=call(rpc,"getMultipleAccounts",[keys,{"encoding":"base64","commitment":"confirmed"}])
    values=resp.get("value")
    if not isinstance(values,list) or len(values)!=len(keys): raise ValueError("invalid RPC response")
    out=[]
    for idx,key,account in zip(indexes,keys,values):
        entry={"start_tick":idx,"address":key,"status":"MISSING"}
        if account:
            if account.get("owner")!=PROGRAM or account.get("executable"):
                raise ValueError("wrong tick-array owner")
            data=account.get("data")
            if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
                raise ValueError("invalid tick array encoding")
            raw=base64.b64decode(data[0],validate=True)
            if len(raw)==FIXED_LEN and raw[:8]==DISC:
                found=int.from_bytes(raw[8:12],"little",signed=True)
                if found!=idx or b58(raw[-32:])!=pool_address:
                    raise ValueError("wrong tick array start or Whirlpool")
                entry["status"]="FIXED_VALID"
            else:
                entry["status"]="UNSUPPORTED_LAYOUT"
        out.append(entry)
    return {"pool":pool_address,"pool_tick":state["tick_current_index"],
            "slot":resp.get("context",{}).get("slot"),"arrays":out,
            "swap_ready":False}

def main():
    import sys
    manifest=os.environ.get("WHIRLPOOL_MANIFEST","arb/whirlpool_pools.json")
    with open(manifest) as f: pools=json.load(f)["pools"]
    results=[inspect(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),p["address"]) for p in pools]
    print(json.dumps(results,indent=2))
    if not pools: return 2
    return 0

if __name__=="__main__":
    raise SystemExit(main())
