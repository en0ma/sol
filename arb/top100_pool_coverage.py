"""Top-100 Solana token pool coverage campaign. Read-only; no registry mutation.

Jupiter Token API provides *ranking metadata only*. Pool evidence comes
exclusively from existing Solana RPC discovery and per-venue verifiers.
"""
import argparse,json,os,time,urllib.request
from pathlib import Path
from arb.onchain_pool_discovery import MINTS,VENUES
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

def indexed_candidates(mint, hubs, *, min_liquidity_usd=10000):
    """DEX Screener proposes addresses only; on-chain verification is mandatory."""
    from urllib.parse import quote
    url="https://api.dexscreener.com/token-pairs/v1/solana/"+quote(mint,safe="")
    request=urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"sol-pool-coverage/1"})
    with urllib.request.urlopen(request,timeout=35) as response:
        rows=json.load(response)
    if not isinstance(rows,list):
        raise ValueError("invalid indexed pair response")
    found={}
    for row in rows:
        if not isinstance(row,dict) or row.get("chainId")!="solana":
            continue
        base=(row.get("baseToken") or {}).get("address")
        quote_mint=(row.get("quoteToken") or {}).get("address")
        if mint not in (base,quote_mint) or not {base,quote_mint}.intersection(hubs):
            continue
        liquidity=(row.get("liquidity") or {}).get("usd")
        if not isinstance(liquidity,(int,float)) or liquidity<min_liquidity_usd:
            continue
        address=row.get("pairAddress")
        if not isinstance(address,str) or not 32<=len(address)<=44:
            continue
        found[address]={"address":address,"indexed_mints":[base,quote_mint],
            "indexed_dex":row.get("dexId"),"indexed_liquidity_usd":liquidity}
    return sorted(found.values(),key=lambda x:-x["indexed_liquidity_usd"])

def campaign(rpc,registry,ranked,*,start=0,count=8,pace=0.5):
    if not 0<=start<len(ranked) or not 1<=count<=100:
        raise ValueError("invalid target slice")
    from arb.pool_registry import refresh
    from arb.rpc import call
    existing={(x["venue"],x["address"]):x for x in registry}
    known_mints={m for row in registry for m in row.get("mints",[])}
    # Spend discovery budget on top-ranked tokens absent from the existing graph.\n    missing=[token for token in ranked if token["mint"] not in known_mints]\n    targets=missing[start:start+count]\n    if not targets:\n        raise ValueError("no missing ranked tokens in the requested slice")
    pools=[];errors=[];target_records=[]
    programs={program:venue for venue,(program,*_) in VENUES.items()}
    exhausted=False
    for token in targets:
        mint=token["mint"]
        if exhausted:break
        try:
            indexed=indexed_candidates(mint,set(MINTS[h] for h in HUBS))
        except Exception as exc:
            errors.append({"target_mint":mint,"stage":"INDEX_LOOKUP",
                           "error":type(exc).__name__+": "+str(exc)[:200]})
            target_records.append({**token,"discovery_status":"INDEX_FAILED"})
            continue
        new_count=0;verified_count=0\n        # Prefer missing token/hub pairs; never spend verification budget on a\n        # pair already represented in the persistent registry.\n        indexed=[c for c in indexed if frozenset(c["indexed_mints"]) not in known_pairs]\n        indexed.sort(key=lambda c:-c["indexed_liquidity_usd"])
        # Index data is never trusted for pool type, mint identity, or balances.
        for candidate in indexed[:12]:\n            if new_count>=3:\n                break
            address=candidate["address"]
            if any(key[1]==address for key in existing):continue
            try:
                response=call(rpc,"getAccountInfo",[address,{"encoding":"base64","commitment":"confirmed"}])
                info=response.get("value")
                venue=programs.get(info.get("owner")) if isinstance(info,dict) else None
                if not venue:continue
                verification=refresh(rpc,[{"venue":venue,"address":address,
                                            "mints":candidate["indexed_mints"]}])
                if not verification["verified_pools"]:
                    raise ValueError(verification["rejected"][0]["reason"])
                row=verification["verified_pools"][0]
                if mint not in row["mints"] or not set(row["mints"]).intersection(
                        MINTS[h] for h in HUBS):
                    raise ValueError("verified token/hub mismatch")
                identity=(venue,address)
                existing[identity]={"venue":venue,"address":address,"mints":row["mints"]}
                pools.append({**row,"target_mint":mint,
                    "index_source":"DEXSCREENER_CANDIDATE_ONLY"})
                new_count+=1;verified_count+=1\n                known_pairs.add(frozenset(row["mints"]))
            except Exception as exc:
                message=type(exc).__name__+": "+str(exc)[:200]
                errors.append({"target_mint":mint,"address":address,
                               "stage":"ONCHAIN_AUTHENTICATION","error":message})
                if "429" in message or "too many requests" in message.lower():
                    exhausted=True
                    break
            if pace:time.sleep(pace)
        target_records.append({**token,"already_in_registry":mint in known_mints,
            "indexed_candidate_count":len(indexed),"new_verified_pool_count":new_count,
            "discovery_status":"RATE_LIMITED" if exhausted else "COMPLETE"})
    all_candidates=list(existing.values())
    return {"status":"PARTIAL" if errors or len(target_records)<len(targets) else "COMPLETE",
        "ranking_source":"JUPITER_TOKEN_API_METADATA_ONLY",
        "candidate_index":"DEXSCREENER_NOT_TRUSTED_FOR_AUTHENTICATION",
        "pool_authentication_source":"DIRECT_SOLANA_RPC",
        "selection_policy":"MISSING_TOP_RANKED_MINTS_FIRST_MISSING_PAIRS_MAX_3_POOLS_PER_TOKEN",\n        "already_covered_ranked_tokens_skipped":sum(t["mint"] in known_mints for t in ranked),\n        "missing_ranked_tokens_remaining":len(missing)-len(target_records),\n        "targets":target_records,"new_verified_pools":pools,"errors":errors,
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
