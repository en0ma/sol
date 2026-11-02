"""Paginated Solana top-pool candidate discovery; only RPC-authenticated identities accepted.

External indexed data is untrusted. Never broadcasts or edits the registry.
"""
import argparse,json,os,time,urllib.request
from pathlib import Path

from arb.onchain_pool_discovery import VENUES
from arb.pool_registry import refresh
from arb.rpc import call

INDEX="https://api.geckoterminal.com/api/v2/networks/solana/pools"

def top_page(page,sort="h24_volume_usd_desc"):
    from urllib.parse import urlencode
    url=INDEX+"?"+urlencode({"page":page,"sort":sort})
    req=urllib.request.Request(url,headers={"Accept":"application/json",
                                             "User-Agent":"sol-pool-coverage/1"})
    with urllib.request.urlopen(req,timeout=30) as response:
        payload=json.load(response)
    items=payload.get("data")
    if not isinstance(items,list):
        raise ValueError("invalid indexed top-pools page")
    result=[]
    for item in items:
        attrs=item.get("attributes",{})
        addr=attrs.get("address")
        if isinstance(addr,str) and 32<=len(addr)<=44:
            result.append({"address":addr,"indexed_volume_h24":(attrs.get("volume_usd") or {}).get("h24"),
                           "index_page":page})
    return result

def campaign(rpc,entries,*,target=150,max_add=200,max_pages=10,pace=0.5):
    if not (1<=target<=max_add<=200 and 1<=max_pages<=100 and 0<=pace<=5):
        raise ValueError("invalid campaign bounds")
    old={(e["venue"],e["address"]):e for e in entries}
    seen_addresses={e["address"] for e in entries}
    known_mints={m for e in entries for m in e.get("mints",[])}
    programs={entry[0]:venue for venue,entry in VENUES.items()}
    new=[];errors=[];pages=[];seen_index=set()
    stop="PAGE_LIMIT"
    for page in range(1,max_pages+1):
        if len(new)>=target or len(old)>=400:
            stop="TARGET_REACHED" if len(new)>=target else "REGISTRY_CAP"
            break
        try:
            candidates=top_page(page)
        except Exception as exc:
            errors.append({"page":page,"stage":"INDEX","error":repr(exc)[:220]})
            stop="INDEX_FAILED"
            break
        if not candidates:
            stop="INDEX_EXHAUSTED"
            break
        attempted=0
        for candidate in candidates:
            address=candidate["address"]
            if address in seen_addresses or address in seen_index:
                continue
            seen_index.add(address)
            attempted+=1
            try:
                info=call(rpc,"getAccountInfo",[address,{"encoding":"base64","commitment":"confirmed"}]).get("value")
                venue=programs.get(info.get("owner")) if isinstance(info,dict) else None
                if venue is None:
                    continue
                verdict=refresh(rpc,[{"venue":venue,"address":address}])
                if not verdict["verified_pools"]:
                    raise ValueError(verdict["rejected"][0]["reason"])
                p=verdict["verified_pools"][0]
                if (venue,address) in old:
                    continue
                # Trust only decoded verified mints, never indexed token labels.
                record={"venue":venue,"address":address,"mints":p["mints"],
                        "source_slot":p["slot"],"indexed_page":page}
                new.append(record)
                old[(venue,address)]=record
                seen_addresses.add(address)
            except Exception as exc:
                error=type(exc).__name__+": "+str(exc)[:200]
                errors.append({"page":page,"address":address,"error":error})
                if "429" in error or "too many requests" in error.lower():
                    stop="SOURCE_RATE_LIMITED"
                    break
            if pace:time.sleep(pace)
            if len(new)>=target or len(new)>=max_add or len(old)>=400:
                stop="TARGET_REACHED" if len(new)>=target else "REGISTRY_CAP"
                break
        pages.append({"page":page,"listed":len(candidates),"new_candidates_checked":attempted,
                      "total_authenticated_new":len(new)})
        if stop!="PAGE_LIMIT":
            break
    all_pools=list(old.values())
    after_mints={m for p in all_pools for m in p.get("mints",[])}
    return {"status":"COMPLETE" if len(new)>=target else "PARTIAL",
            "stop_reason":stop,"target_new_pools":target,
            "authenticated_new_pool_count":len(new),
            "existing_pool_count":len(entries),"candidate_registry_pool_count":len(all_pools),
            "new_token_mints":sorted(after_mints-known_mints),
            "pages":pages,"errors":errors,"new_verified_pools":new,
            "candidate_registry":{"pools":all_pools},
            "index_source":"GECKOTERMINAL_TOP_POOLS_CANDIDATES_ONLY",
            "authentication":"DIRECT_SOLANA_RPC_REFRESH",
            "registry_mutated":False,"broadcast":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--rpc",default=os.getenv("SOLANA_RPC_URL","http://127.0.0.1:8899"))
    p.add_argument("--registry",default="arb/pool_registry.json")
    p.add_argument("--target",type=int,default=150)
    p.add_argument("--max-pages",type=int,default=10)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    entries=json.loads(Path(args.registry).read_text())["pools"]
    result=campaign(args.rpc,entries,target=args.target,max_pages=args.max_pages)
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"status":result["status"],"stop_reason":result["stop_reason"],
         "new_verified_pools":len(result["new_verified_pools"]),
         "new_token_mints":len(result["new_token_mints"]),
         "pages_examined":len(result["pages"])}))
    if result["status"]!="COMPLETE":
        raise SystemExit(2)

if __name__=="__main__":main()
