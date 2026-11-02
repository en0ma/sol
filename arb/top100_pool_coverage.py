"""Top-100 Solana token pool coverage campaign. Read-only; no registry mutation.

Jupiter Token API provides *ranking metadata only*. Pool evidence comes
exclusively from existing Solana RPC discovery and per-venue verifiers.
"""
import argparse,json,os,time,urllib.request
from pathlib import Path
from arb.onchain_pool_discovery import discover,MINTS,VENUES
from arb.pool_registry import refresh

API="https://api.jup.ag/tokens/v2"
HUBS=("WSOL","USDC","USDT")
def ranked_tokens(limit=100,api_key=None):
    if not 1<=limit<=100:raise ValueError("rank limit must be 1..100")
    seen={}
    # Organic ranking includes majors; traded ranking supplements coverage.
    for category in ("toptraded","toporganicscore"):
        req=urllib.request.Request(f"{API}/{category}/24h?limit=100",
            headers={"Accept":"application/json",**({"x-api-key":api_key} if api_key else {})})
        with urllib.request.urlopen(req,timeout=35) as response:
            data=json.load(response)
        if isinstance(data,dict):
            data=data.get("tokens",data.get("data",[]))
        if not isinstance(data,list):raise ValueError("unexpected token-ranking payload")
        for item in data:
            mint=item.get("id")
            if (not isinstance(mint,str) or not 32<=len(mint)<=44
                    or item.get("isVerified") is not True
                    or (item.get("audit") or {}).get("isSus") is True):
                continue
            seen.setdefault(mint,{"mint":mint,"symbol":item.get("symbol"),
                "name":item.get("name"),"source_category":category,
                "organic_score":item.get("organicScore"),
                "liquidity_usd":item.get("liquidity")})
        if len(seen)>=limit:break
        time.sleep(2)
    # Always include known primary hubs as tracked, even if ranking omits them.
    hubs=[{"mint":MINTS[label],"symbol":label,"source_category":"CORE_HUB"}
          for label in HUBS]
    hub_mints={x["mint"] for x in hubs}
    return (hubs+[row for mint,row in seen.items() if mint not in hub_mints])[:limit]

def campaign(rpc,registry,ranked,*,start=0,count=8,pace=0.5):
    if not 0<=start<len(ranked) or not 1<=count<=100:
        raise ValueError("invalid target slice")
    existing={(x["venue"],x["address"]):x for x in registry}
    known_mints={m for row in registry for m in row.get("mints",[])}
    targets=ranked[start:start+count]
    pools=[];errors=[];target_records=[]
    for token in targets:
        mint=token["mint"]
        pairs=[(mint,MINTS[h]) for h in HUBS if mint!=MINTS[h]]
        discovered=discover(rpc,pairs,limit=32,pace_seconds=pace)
        for row in discovered["pools"]:
            identity=(row["venue"],row["address"])
            if identity not in existing:
                existing[identity]={"venue":row["venue"],"address":row["address"],
                                    "mints":row["mints"]}
                pools.append({**row,"target_mint":mint})
        errors.extend({"target_mint":mint,**e} for e in discovered["errors"])
        target_records.append({**token,"already_in_registry":mint in known_mints,
           "new_verified_pool_count":sum(p["target_mint"]==mint for p in pools),
           "discovery_status":discovered["status"]})
        if discovered["status"]=="UPSTREAM_RATE_LIMITED":break
    all_candidates=list(existing.values())
    return {"status":"PARTIAL" if errors or len(target_records)<len(targets) else "COMPLETE",
        "ranking_source":"JUPITER_TOKEN_API_METADATA_ONLY",
        "pool_authentication_source":"DIRECT_SOLANA_RPC",
        "targets":target_records,"new_verified_pools":pools,"errors":errors,
        "candidate_registry":{"pools":all_candidates},
        "mutated_repository_registry":False,"broadcast":False,
        "pool_registry_target_token_count":len({m for p in all_candidates for m in p.get("mints",[])})}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--rpc",default=os.getenv("SOLANA_RPC_URL","http://127.0.0.1:8899"))
    p.add_argument("--registry",default="arb/pool_registry.json")
    p.add_argument("--ranking",default="")
    p.add_argument("--start",type=int,default=0)
    p.add_argument("--count",type=int,default=8)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    ranked=json.loads(Path(args.ranking).read_text()) if args.ranking else ranked_tokens(
        api_key=os.getenv("JUPITER_API_KEY"))
    registry=json.loads(Path(args.registry).read_text())["pools"]
    report=campaign(args.rpc,registry,ranked,start=args.start,count=args.count)
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"status":report["status"],"targets_examined":len(report["targets"]),
        "new_verified_pools":len(report["new_verified_pools"]),
        "token_count_in_candidate_registry":report["pool_registry_target_token_count"]}))
    if report["status"]!="COMPLETE":raise SystemExit(2)

if __name__=="__main__":main()
