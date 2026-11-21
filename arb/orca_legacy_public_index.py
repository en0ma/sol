"""Token-agnostic Orca legacy candidate discovery via GeckoTerminal's DEX index.

DEX labels are not reliable protocol-version attestations. The indexed pool
addresses are ONLY candidates; the Surfpool local-fork verifier must confirm
the exact Orca Token Swap v1 program, pool layout, vaults and authorities.
"""
import json
import math
from urllib.parse import quote,urlencode
from urllib.request import Request,urlopen

BASE="https://api.geckoterminal.com/api/v2"
MAX_BYTES=1_000_000

def _get(url,timeout):
    request=Request(url,headers={"Accept":"application/json",
                                  "User-Agent":"sol-simulation-pool-discovery/1"})
    with urlopen(request,timeout=timeout) as response:
        raw=response.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:
        raise ValueError("GeckoTerminal index response too large")
    data=json.loads(raw)
    if not isinstance(data,dict) or not isinstance(data.get("data"),list):
        raise ValueError("GeckoTerminal response missing data list")
    return data

def list_dexes(*,max_pages=3,timeout=12):
    if type(max_pages)is not int or not 1<=max_pages<=10:
        raise ValueError("invalid DEX enumeration page limit")
    found={}
    for page in range(1,max_pages+1):
        payload=_get(BASE+"/networks/solana/dexes?"+urlencode({"page":page}),timeout)
        rows=payload["data"]
        for row in rows:
            if isinstance(row,dict) and isinstance(row.get("id"),str):
                attrs=row.get("attributes")
                found[row["id"]]=attrs.get("name") if isinstance(attrs,dict) else None
        if not rows or not payload.get("links",{}).get("next"):
            break
    return found

def parse_candidates(payload,*,min_liquidity_usd=10000,max_matches=16):
    if (type(min_liquidity_usd) not in (int,float)
            or not math.isfinite(min_liquidity_usd) or min_liquidity_usd<0
            or type(max_matches)is not int or not 1<=max_matches<=256):
        raise ValueError("invalid candidate limits")
    if not isinstance(payload,dict) or not isinstance(payload.get("data"),list):
        raise ValueError("invalid GeckoTerminal pool listing")
    found=[]
    for row in payload["data"]:
        if not isinstance(row,dict):
            continue
        attrs=row.get("attributes")
        if not isinstance(attrs,dict):
            continue
        value=attrs.get("reserve_in_usd")
        try:
            usd=float(value)
        except (TypeError,ValueError,OverflowError):
            continue
        if not math.isfinite(usd) or usd<min_liquidity_usd:
            continue
        address=attrs.get("address")
        if isinstance(address,str) and 32<=len(address)<=44 and address not in found:
            found.append(address)
            if len(found)>=max_matches:
                break
    return found

def discover(*,dex_id,min_liquidity_usd=10000,max_pages=4,
             max_matches=16,timeout=12):
    """Use a verified catalog DEX id; never infer v1 ownership from the id."""
    if (not isinstance(dex_id,str) or not 1<=len(dex_id)<=100
            or type(max_pages)is not int or not 1<=max_pages<=10
            or type(max_matches)is not int or not 1<=max_matches<=256):
        raise ValueError("invalid DEX id or scan bound")
    found=[]
    for page in range(1,max_pages+1):
        url=(BASE+"/networks/solana/dexes/"+quote(dex_id,safe="")+
             "/pools?"+urlencode({"page":page}))
        payload=_get(url,timeout)
        for address in parse_candidates(payload,min_liquidity_usd=min_liquidity_usd,
                                        max_matches=max_matches):
            if address not in found:
                found.append(address)
                if len(found)>=max_matches:
                    return found
        links=payload.get("links",{})
        if not isinstance(links,dict) or not links.get("next"):
            break
    return found
