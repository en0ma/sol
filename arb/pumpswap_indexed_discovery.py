"""Bounded GeckoTerminal PumpSwap candidate discovery with RPC verification.

Pool addresses from an indexer are untrusted; only owner/decoder/vault checks
via pool_registry.refresh promote them to verified pools. No indexer prices.
"""
import argparse,json,os
from collections import Counter
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
        relationships=row.get("relationships",{})
        dex=relationships.get("dex",{}).get("data",{}) if isinstance(relationships,dict) else {}
        dex_id=dex.get("id") if isinstance(dex,dict) else None
        # GeckoTerminal may omit the DEX relationship; in that case the
        # identity remains untrusted and must pass the full on-chain check.
        if isinstance(dex_id,str) and "pump" not in dex_id.lower():
            continue
        address=attributes.get("address")
        if (not isinstance(address,str) or not 32<=len(address)<=44 or
            any(c not in BASE58 for c in address) or address in seen):
            continue
        seen.add(address)
        result.append({"venue":"pumpswap","address":address,"verified":False,
                       "source":"geckoterminal","actionable":False})
    return result

def fetch(mint,timeout=20,page=1):
    if type(page)is not int or not 1<=page<=10:
        raise ValueError("invalid indexer page")
    if not isinstance(mint,str) or not 32<=len(mint)<=44 or any(c not in BASE58 for c in mint):
        raise ValueError("invalid mint")
    url=API+quote(mint,safe="")+"/pools?page="+str(page)
    with urlopen(Request(url,headers={"Accept":"application/json;version=20230203",
                                     "User-Agent":"sol-arbitrage-pool-discovery/1"}),
                 timeout=timeout) as response:
        return candidates(json.load(response))

def scan(rpc,mints,limit=30,pages=1):
    from arb.pool_registry import refresh
    if type(limit)is not int or not 1<=limit<=100 or not 1<=len(mints)<=5:
        raise ValueError("invalid indexed scan budget")
    if type(pages)is not int or not 1<=pages<=10:
        raise ValueError("invalid indexed scan pages")
    all_candidates=[];seen=set()
    for mint in mints:
        for page in range(1,pages+1):
            for candidate in fetch(mint) if pages==1 else fetch(mint,page=page):
                if candidate["address"] not in seen:
                    seen.add(candidate["address"])
                    all_candidates.append(candidate)
    subset=all_candidates[:limit]
    verified=refresh(rpc,subset)
    categories=Counter()
    for item in verified["rejected"]:
        reason=item.get("reason","UNKNOWN").lower()
        if "owner mismatch" in reason or "incorrectly owned" in reason:
            category="OTHER_PROGRAM"
        elif "supply" in reason or "mint" in reason:
            category="UNSUPPORTED_MINT_OR_TOKEN"
        elif "fee" in reason or "config" in reason:
            category="FEE_OR_CONFIG_UNVERIFIED"
        else:
            category="OTHER_VALIDATION_FAILURE"
        categories[category]+=1
    return {"source":"geckoterminal","candidate_count":len(all_candidates),
            "pages_per_mint":pages,"rpc_validation_budget":limit,
            "rejection_categories":dict(categories),
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
    p.add_argument("--pages",type=int,default=1)
    p.add_argument("--output",default="")
    args=p.parse_args()
    labels=[x.strip() for x in args.mints.split(",")]
    if any(x not in MINTS for x in labels):raise SystemExit("unsupported mint label")
    report=scan(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),
                [MINTS[x] for x in labels],args.limit,args.pages)
    print(json.dumps(report,indent=2))
    if args.output:
        with open(args.output,"w") as f:json.dump(report,f,indent=2)

if __name__=="__main__":main()
