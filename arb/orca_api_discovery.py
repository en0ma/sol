"""Bounded Orca public Whirlpool identity discovery; API metadata is untrusted.

All candidates must pass independent on-chain pool registry validation.
"""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from arb.pool_registry_batches import refresh_batched

ROOT = "https://api.orca.so/v2/solana/pools"
BASE58 = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")

def fetch_page(cursor=None, size=50, min_tvl=10000):
    params={"size":size,"sortBy":"tvl","sortDirection":"desc","minTvl":min_tvl}
    if cursor is not None:
        params["next"]=cursor
    url=ROOT+"?"+urlencode(params)
    request=Request(url, headers={"Accept":"application/json",
                                  "User-Agent":"sol-arbitrage-orca-discovery/1"})
    with urlopen(request, timeout=25) as response:
        return json.load(response)

def parse_page(payload):
    if not isinstance(payload,dict) or not isinstance(payload.get("data"),list):
        raise ValueError("invalid Orca pool API page")
    rows=payload["data"]
    if len(rows)>200:
        raise ValueError("Orca response exceeds page budget")
    meta=payload.get("meta")
    if not isinstance(meta,dict):
        raise ValueError("missing Orca pagination metadata")
    cursor=meta.get("next")
    if cursor is not None and (not isinstance(cursor,str) or
                               not 1<=len(cursor)<=2048):
        raise ValueError("invalid Orca cursor")
    candidates=[];seen=set()
    for row in rows:
        if not isinstance(row,dict):
            continue
        address=row.get("address")
        if (not isinstance(address,str) or not 32<=len(address)<=44 or
                any(ch not in BASE58 for ch in address) or address in seen):
            continue
        seen.add(address)
        candidates.append({"venue":"orca","address":address,"verified":False,
                           "actionable":False,"source":"orca_public_api"})
    return candidates,cursor

def scan(rpc, pinned=(), pages=3, size=50, min_tvl=10000, limit=150):
    if (type(pages) is not int or not 1<=pages<=10 or
            type(size) is not int or not 1<=size<=200 or
            type(limit) is not int or not 1<=limit<=2000 or
            type(min_tvl) not in (int,float) or not 0<=min_tvl<=1e9):
        raise ValueError("invalid Orca discovery budget")
    pinned=set(pinned)
    found=[];seen=set();cursors=set();cursor=None;pages_fetched=0
    for _ in range(pages):
        rows,next_cursor=parse_page(fetch_page(cursor=cursor,size=size,min_tvl=min_tvl))
        pages_fetched+=1
        for entry in rows:
            if entry["address"] not in seen:
                seen.add(entry["address"])
                found.append(entry)
        if not next_cursor:
            break
        if next_cursor in cursors:
            raise ValueError("Orca pagination cursor repeated")
        cursors.add(next_cursor)
        cursor=next_cursor
    novel=[entry for entry in found if entry["address"] not in pinned][:limit]
    validated=refresh_batched(rpc,novel,batch_size=100)
    return {"source":"orca_public_api","pages_fetched":pages_fetched,
            "candidate_count":len(found),"new_candidate_count":len(novel),
            "checked_count":validated["verified_count"]+validated["rejected_count"],
            "new_verified_count":validated["verified_count"],
            "rejected_count":validated["rejected_count"],
            "verified_identities":[{"venue":pool["venue"],"address":pool["address"],
                                     "mints":pool["mints"]}
                                    for pool in validated["verified_pools"]],
            "rejections":validated["rejected"],
            "rpc_validation_batches":validated["batch_count"],
            "actionable":False,"simulation_verified":False,"mainnet_broadcast":False}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--registry",default="arb/pool_registry.json")
    parser.add_argument("--pages",type=int,default=3)
    parser.add_argument("--size",type=int,default=50)
    parser.add_argument("--min-tvl",type=float,default=10000)
    parser.add_argument("--limit",type=int,default=150)
    parser.add_argument("--output",default="")
    args=parser.parse_args()
    pinned=json.loads(Path(args.registry).read_text())["pools"]
    pinned_addresses=[entry["address"] for entry in pinned if entry.get("venue")=="orca"]
    report=scan(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),
                pinned_addresses,args.pages,args.size,args.min_tvl,args.limit)
    print(json.dumps(report,indent=2))
    if args.output:
        Path(args.output).write_text(json.dumps(report,indent=2))
if __name__=="__main__":
    main()
