"""Public Raydium API v3 discovery for AMM v4 candidate addresses only.

Public metadata is never execution evidence. Every candidate must be decoded
and independently authenticated against the local Surfpool fork.
"""
import json
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from arb.orca_whirlpool import SOL,USDC

API="https://api-v3.raydium.io/pools/info/mint"
AMM_V4="675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"

def parse_candidates(response,*,mint_a=SOL,mint_b=USDC,max_matches=8):
    if not isinstance(response,dict) or response.get("success") is not True:
        raise ValueError("Raydium API response not successful")
    data=response.get("data")
    if not isinstance(data,dict) or not isinstance(data.get("data"),list):
        raise ValueError("Raydium API pool list malformed")
    found=[]
    for pool in data["data"]:
        if not isinstance(pool,dict) or pool.get("programId")!=AMM_V4:
            continue
        left,right=pool.get("mintA"),pool.get("mintB")
        if not isinstance(left,dict) or not isinstance(right,dict):
            continue
        if {left.get("address"),right.get("address")}!={mint_a,mint_b}:
            continue
        address=pool.get("id")
        if isinstance(address,str) and 32<=len(address)<=44 and address not in found:
            found.append(address)
            if len(found)>=max_matches:
                break
    return found

def discover(*,mint_a=SOL,mint_b=USDC,max_matches=8,timeout=12):
    if type(max_matches)is not int or not 1<=max_matches<=16:
        raise ValueError("invalid Raydium API candidate limit")
    if not all(isinstance(m,str) and 32<=len(m)<=44 for m in (mint_a,mint_b)):
        raise ValueError("invalid Raydium API mint")
    if mint_a==mint_b:
        raise ValueError("distinct mints required")
    query=urlencode({"mint1":mint_a,"mint2":mint_b,"poolType":"standard",
                     "poolSortField":"liquidity","sortType":"desc",
                     "pageSize":100,"page":1})
    request=Request(API+"?"+query,headers={"Accept":"application/json",
                                             "User-Agent":"sol-simulation-pool-discovery/1"})
    with urlopen(request,timeout=timeout) as response:
        raw=response.read(1_000_001)
    if len(raw)>1_000_000:
        raise ValueError("Raydium API response too large")
    return parse_candidates(json.loads(raw),mint_a=mint_a,mint_b=mint_b,
                            max_matches=max_matches)
