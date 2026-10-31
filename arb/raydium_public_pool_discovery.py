"""API-first Raydium AMM v4 discovery without a hardcoded token pair.

Enumerate venue pools by liquidity across bounded pages. API records are
untrusted candidates; only local-fork owner, decoder, vault and market checks
can establish pool authenticity. No quote, trade or broadcast is authorized.
"""
import json
import math
from urllib.parse import urlencode
from urllib.request import Request,urlopen

API="https://api-v3.raydium.io/pools/info/list"
AMM_V4="675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"

def parse_candidates(response,*,min_liquidity_usd=10000,max_matches=32):
    if (type(min_liquidity_usd) not in (int,float)
            or not math.isfinite(min_liquidity_usd) or min_liquidity_usd<0
            or type(max_matches)is not int or not 1<=max_matches<=256):
        raise ValueError("invalid liquidity or candidate bound")
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
        a,b=left.get("address"),right.get("address")
        if (not isinstance(a,str) or not isinstance(b,str)
                or not 32<=len(a)<=44 or not 32<=len(b)<=44 or a==b):
            continue
        liquidity=pool.get("tvl")
        if (type(liquidity) not in (int,float) or not math.isfinite(liquidity)
                or liquidity<min_liquidity_usd):
            continue
        address=pool.get("id")
        if isinstance(address,str) and 32<=len(address)<=44 and address not in found:
            found.append(address)
            if len(found)>=max_matches:
                break
    return found

def discover(*,min_liquidity_usd=10000,max_matches=32,max_pages=5,
             page_size=100,timeout=12):
    if (type(max_pages)is not int or not 1<=max_pages<=20
            or type(page_size)is not int or not 1<=page_size<=1000
            or type(max_matches)is not int or not 1<=max_matches<=256
            or type(min_liquidity_usd) not in (int,float)
            or not math.isfinite(min_liquidity_usd) or min_liquidity_usd<0):
        raise ValueError("invalid Raydium discovery bounds")
    found=[]
    for page in range(1,max_pages+1):
        query=urlencode({"poolType":"standard","poolSortField":"liquidity",
                         "sortType":"desc","pageSize":page_size,"page":page})
        request=Request(API+"?"+query,headers={
            "Accept":"application/json",
            "User-Agent":"sol-simulation-pool-discovery/1"})
        with urlopen(request,timeout=timeout) as response:
            raw=response.read(1_000_001)
        if len(raw)>1_000_000:
            raise ValueError("Raydium API response too large")
        envelope=json.loads(raw)
        rows=envelope.get("data",{}).get("data") if isinstance(envelope,dict) else None
        page_found=parse_candidates(envelope,min_liquidity_usd=min_liquidity_usd,
                                    max_matches=max_matches)
        for address in page_found:
            if address not in found:
                found.append(address)
                if len(found)>=max_matches:
                    return found
        if len(rows)<page_size:
            break
    return found
