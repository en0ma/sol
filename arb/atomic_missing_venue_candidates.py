"""One bounded, untrusted public candidate discovery before read-only local RPC authentication.

Never treats Raydium API hints or pinned CLMM examples as verified pools.
The existing source-fork probe owns authentication and exact mint matching.
"""
import argparse
import json
from pathlib import Path

def enrich(registry,candidates,*,limit=8,clmm_candidates=()):
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
    clmm_existing=sum(x.get("venue")=="raydium_clmm" for x in output["pools"])
    for candidate in clmm_candidates:
        if clmm_existing>=12:
            break
        if (not isinstance(candidate,dict) or
                not isinstance(candidate.get("address"),str) or
                not 32<=len(candidate["address"])<=44 or
                candidate["address"] in known):
            continue
        output["pools"].append({"venue":"raydium_clmm",
            "address":candidate["address"],
            "mints":candidate.get("mints"),
            "source":"untrusted_raydium_api_concentrated",
            "onchain_authenticated":False})
        known.add(candidate["address"])
        clmm_existing+=1
    return output

def discover_clmm_candidates(registry,*,max_pages=2,timeout=8):
    """Bounded public Raydium CLMM leads, ranked by intersection with existing registry."""
    from urllib.parse import urlencode
    from urllib.request import Request,urlopen
    from arb.raydium_clmm import PROGRAM
    from arb.raydium_public_pool_discovery import API
    peers={frozenset(x["mints"]) for x in registry["pools"]
           if x.get("venue")!="raydium_clmm" and
           isinstance(x.get("mints"),list) and len(x["mints"])==2}
    leads=[]
    for page in range(1,max_pages+1):
        url=API+"?"+urlencode({"poolType":"concentrated",
            "poolSortField":"liquidity","sortType":"desc","pageSize":100,"page":page})
        with urlopen(Request(url,headers={"Accept":"application/json",
                       "User-Agent":"sol-readonly-candidate-discovery/1"}),timeout=timeout) as response:
            raw=response.read(1_000_001)
        if len(raw)>1_000_000:
            raise ValueError("CLMM public candidate page exceeds byte bound")
        data=json.loads(raw)
        if not isinstance(data,dict) or data.get("success") is not True:
            raise ValueError("CLMM public discovery response invalid")
        rows=data.get("data",{}).get("data")
        if not isinstance(rows,list):
            raise ValueError("CLMM public discovery rows invalid")
        for row in rows:
            if not isinstance(row,dict) or row.get("programId")!=PROGRAM:
                continue
            a,b=row.get("mintA"),row.get("mintB")
            if not isinstance(a,dict) or not isinstance(b,dict):
                continue
            mints=[a.get("address"),b.get("address")]
            address=row.get("id")
            if (not isinstance(address,str) or not 32<=len(address)<=44 or
                any(not isinstance(m,str) or not 32<=len(m)<=44 for m in mints)
                or mints[0]==mints[1]):
                continue
            leads.append({"address":address,"mints":mints,
                          "matching_peer_mints":frozenset(mints) in peers})
        if len(rows)<100:
            break
    leads.sort(key=lambda x:not x["matching_peer_mints"])
    return leads

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
    registry=json.loads(Path(args.registry).read_text())
    try:
        clmm_candidates=discover_clmm_candidates(registry)
        clmm_error=None
    except (OSError,ValueError,TimeoutError,KeyError,TypeError) as exc:
        clmm_candidates=[]
        clmm_error=type(exc).__name__+": "+str(exc)[:150]
    result=enrich(registry,candidates,limit=args.max_candidates,
                  clmm_candidates=clmm_candidates)
    result["discovery"]={"source":"UNTRUSTED_PUBLIC_API","candidate_count":len(candidates),
                         "error":error,"clmm_candidate_count":len(clmm_candidates),
                         "clmm_matching_peer_mint_count":sum(x["matching_peer_mints"] for x in clmm_candidates),
                         "clmm_error":clmm_error,
                         "onchain_authenticated":False,"broadcast":False}
    Path(args.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result["discovery"]))

if __name__=="__main__":main()
