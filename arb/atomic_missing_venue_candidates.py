"""One bounded, untrusted public candidate discovery before read-only local RPC authentication.

Never treats Raydium API hints or pinned CLMM examples as verified pools.
The existing source-fork probe owns authentication and exact mint matching.
"""
import argparse
import json
from pathlib import Path

def enrich(registry,candidates,*,limit=8):
    if not isinstance(registry,dict) or not isinstance(registry.get("pools"),list):
        raise ValueError("invalid existing pool registry")
    if type(limit) is not int or not 1<=limit<=12:
        raise ValueError("invalid bounded AMM v4 pool candidate count")
    output={"pools":[dict(x) for x in registry["pools"]]}
    known={p.get("address") for p in output["pools"]}
    count=0
    for address in candidates:
        if count>=limit:break
        if not isinstance(address,str) or not 32<=len(address)<=44 or address in known:
            continue
        output["pools"].append({"venue":"raydium_amm_v4","address":address,
                                "source":"untrusted_raydium_api_v3",
                                "onchain_authenticated":False})
        known.add(address)
        count+=1
    return output

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--registry",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--max-candidates",type=int,default=8)
    args=p.parse_args()
    from arb.raydium_public_pool_discovery import discover
    try:
        candidates=discover(max_matches=args.max_candidates,max_pages=2,
                            min_liquidity_usd=10000,timeout=8)
        error=None
    except (OSError,ValueError,TimeoutError,KeyError,TypeError) as exc:
        candidates=[]
        error=type(exc).__name__+": "+str(exc)[:150]
    result=enrich(json.loads(Path(args.registry).read_text()),candidates,limit=args.max_candidates)
    result["discovery"]={"source":"UNTRUSTED_PUBLIC_API","candidate_count":len(candidates),
                         "error":error,"onchain_authenticated":False,"broadcast":False}
    Path(args.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result["discovery"]))

if __name__=="__main__":main()
