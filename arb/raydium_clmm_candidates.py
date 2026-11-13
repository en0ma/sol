"""Check published Raydium CLMM pool fixtures against fork RPC, without trusting them.

Sources are leads only. Account owner/decoder and vaults must pass before
tick arrays are inspected. A failed fixture does not admit executable routes.
"""
import base64,json,os
from arb.rpc import call
from arb.raydium_clmm import PROGRAM,decode,verify
from arb.raydium_clmm_ticks import inspect

def probe(rpc,fixtures):
    results=[]
    for item in fixtures:
        address=item["address"]
        result={"address":address,"source":item.get("source"),
                "pool_verified":False,"tick_arrays_ready":False,"swap_executed":False}
        try:
            info=call(rpc,"getAccountInfo",[address,{"encoding":"base64","commitment":"confirmed"}]).get("value")
            if not info or info.get("owner")!=PROGRAM:raise ValueError("missing CLMM program-owned pool")
            state=decode(base64.b64decode(info["data"][0],validate=True))
            result["verified"]=verify(rpc,address,state)
            result["pool_verified"]=True
            ticks=inspect(rpc,address,zero_for_one=True)
            result["tick_arrays"]=ticks
            result["tick_arrays_ready"]=ticks["all_arrays_valid"]
        except Exception as exc:
            result["error"]=type(exc).__name__+": "+str(exc)[:200]
        results.append(result)
    return {"status":"VERIFIED" if any(x["pool_verified"] for x in results) else "UNVERIFIED",
            "results":results,"swap_executed":False}

def main():
    with open("arb/raydium_clmm_candidates.json") as f:fixtures=json.load(f)["candidates"]
    result=probe(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),fixtures)
    print(json.dumps(result,indent=2))
    path=os.environ.get("CLMM_CANDIDATE_REPORT")
    if path:
        with open(path,"w") as f:json.dump(result,f,indent=2)
    return 0
if __name__=="__main__":raise SystemExit(main())
