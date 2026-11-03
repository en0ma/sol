"""Paginated Solana top-pool candidate discovery; only RPC-authenticated identities accepted.

External indexed data is untrusted. Never broadcasts or edits the registry.
"""
import argparse,json,os,time,urllib.request,urllib.error
from collections import Counter
from pathlib import Path

from arb.onchain_pool_discovery import VENUES
from arb.pool_registry import refresh
from arb.rpc import call

INDEX="https://api.geckoterminal.com/api/v2/networks/solana"
FEEDS=(("volume","/pools",{"sort":"h24_volume_usd_desc"}),
       ("transactions","/pools",{"sort":"h24_tx_count_desc"}),
       ("trending","/trending_pools",{"duration":"24h"}),
       ("trending_1h","/trending_pools",{"duration":"1h"}),
       ("new","/new_pools",{}))
PUBLIC_MAX_PAGE=10

def indexed_json(url):
    """Retry bounded public-index throttling; never relax on-chain checks."""
    for attempt in range(3):
        try:
            request=urllib.request.Request(url,headers={
                "Accept":"application/json","User-Agent":"sol-pool-coverage/1"})
            with urllib.request.urlopen(request,timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code!=429 or attempt==2:
                raise
            time.sleep(min(8,2**attempt))

def token_pairs(mint,known_mints):
    """Discover additional liquidity for existing connected tokens via DEX Screener."""
    from urllib.parse import quote
    url="https://api.dexscreener.com/token-pairs/v1/solana/"+quote(mint,safe="")
    data=indexed_json(url)
    if not isinstance(data,list):
        raise ValueError("unexpected indexed token-pairs payload")
    result=[]
    for item in data:
        address=item.get("pairAddress")
        liquidity=(item.get("liquidity") or {}).get("usd") or 0
        if (item.get("chainId")!="solana" or not isinstance(address,str)
                or not 32<=len(address)<=44 or not isinstance(liquidity,(float,int))
                or liquidity<10000):
            continue
        base=(item.get("baseToken") or {}).get("address")
        quote_mint=(item.get("quoteToken") or {}).get("address")
        result.append({"address":address,"liquidity_usd":liquidity,
                       "both_known":base in known_mints and quote_mint in known_mints})
    result.sort(key=lambda row:(row["both_known"],row["liquidity_usd"]),reverse=True)
    return result[:30]

def top_page(page,feed="volume"):
    from urllib.parse import urlencode
    _,endpoint,query=next(item for item in FEEDS if item[0]==feed)
    url=INDEX+endpoint+"?"+urlencode({"page":page,**query})
    payload=indexed_json(url)
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
    blocked_feeds=set()
    for index in range(min(max_pages,len(FEEDS)*PUBLIC_MAX_PAGE)):
        feed,_,_=FEEDS[index//PUBLIC_MAX_PAGE]
        page=index%PUBLIC_MAX_PAGE+1
        if feed in blocked_feeds:
            continue
        if len(new)>=target or len(old)>=400:
            stop="TARGET_REACHED" if len(new)>=target else "REGISTRY_CAP"
            break
        try:
            candidates=top_page(page,feed)
        except Exception as exc:
            errors.append({"feed":feed,"page":page,"stage":"INDEX","error":repr(exc)[:220]})
            if isinstance(exc,urllib.error.HTTPError) and exc.code in (401,403,429):
                blocked_feeds.add(feed)
            continue
        if not candidates:
            continue
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
                errors.append({"feed":feed,"page":page,"address":address,"error":error})
                if "429" in error or "too many requests" in error.lower():
                    stop="SOURCE_RATE_LIMITED"
                    break
            if pace:time.sleep(pace)
            if len(new)>=target or len(new)>=max_add or len(old)>=400:
                stop="TARGET_REACHED" if len(new)>=target else "REGISTRY_CAP"
                break
        pages.append({"feed":feed,"page":page,"listed":len(candidates),"new_candidates_checked":attempted,
                      "total_authenticated_new":len(new)})
        if stop!="PAGE_LIMIT":
            break

    # Secondary discovery: additional pools for already-connected, active mints.
    # A mint's venue diversity is a useful proxy for potential arbitrage cycles.
    if stop=="PAGE_LIMIT" and len(new)<target and len(old)<400:
        hub_mints={"So11111111111111111111111111111111111111112",
                   "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"}
        mint_venues={}
        mint_degree=Counter()
        for entry in entries:
            for mint in entry.get("mints",[]):
                mint_venues.setdefault(mint,set()).add(entry["venue"])
                mint_degree[mint]+=1
        prioritized=sorted((mint for mint in known_mints if mint not in hub_mints),
            key=lambda m:(len(mint_venues.get(m,())),mint_degree[m],m),reverse=True)
        # Cap API usage; untrusted indexed rankings are never verification evidence.
        for position,mint in enumerate(prioritized[:100]):
            if len(new)>=target or len(old)>=400 or stop!="PAGE_LIMIT":
                break
            try:
                candidates=token_pairs(mint,known_mints)
            except Exception as exc:
                errors.append({"feed":"dexscreener_token_pairs","mint":mint,
                               "stage":"INDEX","error":repr(exc)[:220]})
                if isinstance(exc,urllib.error.HTTPError) and exc.code==429:
                    stop="SECONDARY_INDEX_RATE_LIMITED"
                    break
                continue
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
                    record={"venue":venue,"address":address,"mints":p["mints"],
                            "source_slot":p["slot"],"index_feed":"dexscreener_token_pairs",
                            "indexed_mint":mint}
                    new.append(record)
                    old[(venue,address)]=record
                    seen_addresses.add(address)
                except Exception as exc:
                    error=type(exc).__name__+": "+str(exc)[:200]
                    errors.append({"feed":"dexscreener_token_pairs","mint":mint,
                                   "address":address,"error":error})
                    if "429" in error or "too many requests" in error.lower():
                        stop="SOURCE_RATE_LIMITED"
                        break
                if pace:time.sleep(pace)
                if len(new)>=target or len(old)>=400:
                    stop="TARGET_REACHED" if len(new)>=target else "REGISTRY_CAP"
                    break
            pages.append({"feed":"dexscreener_token_pairs","mint":mint,"page":position+1,
                          "listed":len(candidates),"new_candidates_checked":attempted,
                          "total_authenticated_new":len(new)})
            if pace:time.sleep(pace)

    if stop=="PAGE_LIMIT":stop="INDEX_FEEDS_EXHAUSTED"
    all_pools=list(old.values())
    after_mints={m for p in all_pools for m in p.get("mints",[])}
    return {"status":"COMPLETE" if len(new)>=target else "PARTIAL",
            "stop_reason":stop,"target_new_pools":target,
            "authenticated_new_pool_count":len(new),
            "existing_pool_count":len(entries),"candidate_registry_pool_count":len(all_pools),
            "new_token_mints":sorted(after_mints-known_mints),
            "pages":pages,"errors":errors,"new_verified_pools":new,
            "candidate_registry":{"pools":all_pools},
            "index_source":"GECKOTERMINAL_FEEDS_AND_DEXSCREENER_TOKEN_PAIRS_CANDIDATES_ONLY",
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
    # Incomplete coverage is an outcome, not a CI execution failure. Only actual
    # exceptions or inability to write the report should fail this workflow.

if __name__=="__main__":main()
