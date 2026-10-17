"""Bounded GeckoTerminal PumpSwap candidate discovery with RPC verification.

Pool addresses from an indexer are untrusted; only owner/decoder/vault checks
via pool_registry.refresh promote them to verified pools. No indexer prices.
"""
import argparse,json,os
from urllib.request import Request,urlopen
from urllib.parse import quote
from arb.onchain_pool_discovery import MINTS

API="https://api.geckoterminal.com/api/v2/networks/solana/tokens/"
BASE58=set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")

def candidates(payload):
    rows=payload.get("data") if isinstance(payload,dict) else None
    if not isinstance(rows,list) or len(rows)>100:
        raise ValueError("invalid GeckoTerminal pool response")
    result=[];seen=set()
    for row in rows:
        if not isinstance(row,dict):continue
        attributes=row.get("attributes")
        if not isinstance(attributes,dict):continue
        address=attributes.get("address")
        if (not isinstance(address,str) or not 32<=len(address)<=44 or
            any(c not in BASE58 for c in address) or address in seen):
            continue
        seen.add(address)
        result.append({"venue":"pumpswap","address":address,"verified":False,
                       "source":"geckoterminal","actionable":False})
    return result

def fetch(mint,timeout=20):
    if not isinstance(mint,str) or not 32<=len(mint)<=44 or any(c not in BASE58 for c in mint):
        raise ValueError("invalid mint")
    url=API+quote(mint,safe="")+"/pools?page=1"
    with urlopen(Request(url,headers={"Accept":"application/json;version=20230203",
                                     "User-Agent":"sol-arbitrage-pool-discovery/1"}),
                 timeout=timeout) as response:
        return candidates(json.load(response))

def scan(rpc,mints,limit=30):
    from arb.pool_registry import refresh
    if type(limit)is not int or not 1<=limit<=100 or not 1<=len(mints)<=5:
        raise ValueError("invalid indexed scan budget")
    all_candidates=[];seen=set()
    for mint in mints:
        for candidate in fetch(mint):
            if candidate["address"] not in seen:
                seen.add(candidate["address"])
                all_candidates.append(candidate)
    subset=all_candidates[:limit]
    verified=refresh(rpc,subset)
    return {"source":"geckoterminal","candidate_count":len(all_candidates),
            "checked_count":len(subset),"verified_pumpswap_count":verified["verified_count"],
            "verified_identities":[{"venue":p["venue"],"address":p["address"],
                                    "mints":p["mints"]} for p in verified["verified_pools"]],
            "rejected_count":verified["rejected_count"],
            "rejections":verified["rejected"],
            "simulation_verified":False,"mainnet_broadcast":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--mints",default="WSOL,USDC")
    p.add_argument("--limit",type=int,default=20)
    p.add_argument("--output",default="")
    args=p.parse_args()
    labels=[x.strip() for x in args.mints.split(",")]
    if any(x not in MINTS for x in labels):raise SystemExit("unsupported mint label")
    report=scan(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),
                [MINTS[x] for x in labels],args.limit)
    print(json.dumps(report,indent=2))
    if args.output:
        with open(args.output,"w") as f:json.dump(report,f,indent=2)

if __name__=="__main__":main()
