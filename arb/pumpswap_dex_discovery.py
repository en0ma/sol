"""PumpSwap-focused indexed pool discovery, independently checked on-chain.

The DEX list supplies *candidate identities*, not prices or executable quotes.
Never promote an entry without arb.pool_registry.refresh succeeding.
"""
import argparse,json,os,time
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen
from arb.pumpswap_indexed_discovery import candidates

ROOT="https://api.geckoterminal.com/api/v2/networks/solana"

def read_json(url,timeout=20):
    with urlopen(Request(url,headers={"Accept":"application/json;version=20230203",
                                     "User-Agent":"sol-arbitrage-dex-pool-discovery/1"}),
                 timeout=timeout) as response:
        return json.load(response)

def resolve_pumpswap_dex_id(payload):
    rows=payload.get("data") if isinstance(payload,dict) else None
    if not isinstance(rows,list) or len(rows)>1000:
        raise ValueError("invalid DEX directory")
    matches=[]
    for row in rows:
        if not isinstance(row,dict):continue
        dex_id=row.get("id")
        name=row.get("attributes",{}).get("name","") if isinstance(row.get("attributes"),dict) else ""
        if isinstance(dex_id,str) and ("pumpswap" in dex_id.lower().replace("_","").replace("-","")
            or "pumpswap" in str(name).lower().replace(" ","")):
            matches.append(dex_id)
    if len(matches)!=1:
        raise ValueError("PumpSwap DEX identifier missing or ambiguous")
    return matches[0]

def scan(rpc,pages=3,limit=60,pace_seconds=7):
    from arb.pool_registry_batches import refresh_batched
    if type(pages)is not int or not 1<=pages<=10 or type(limit)is not int or not 1<=limit<=2000:
        raise ValueError("invalid scan budget")
    if not isinstance(pace_seconds,(int,float)) or not 0<=pace_seconds<=60:
        raise ValueError("invalid pacing")
    dex_id=resolve_pumpswap_dex_id(read_json(ROOT+"/dexes?page=1"))
    results=[];seen=set();errors=[]
    for page in range(1,pages+1):
        if pace_seconds:time.sleep(pace_seconds)
        try:
            page_rows=candidates(read_json(ROOT+"/dexes/"+dex_id+"/pools?page="+str(page)))
        except HTTPError as exc:
            errors.append({"page":page,"http_status":exc.code})
            if exc.code==429:break
            continue
        except (ValueError,OSError) as exc:
            errors.append({"page":page,"error_type":type(exc).__name__})
            continue
        for entry in page_rows:
            if entry["address"] not in seen:
                seen.add(entry["address"]);results.append(entry)
    report=refresh_batched(rpc,results[:limit],batch_size=100)
    return {"source":"geckoterminal_pumpswap_dex","dex_id":dex_id,
            "candidate_count":len(results),"checked_count":min(len(results),limit),
            "rpc_validation_batches":report["batch_count"],
            "verified_count":report["verified_count"],"rejected_count":report["rejected_count"],
            "verified_identities":[{"venue":x["venue"],"address":x["address"],"mints":x["mints"]}
                                   for x in report["verified_pools"]],
            "rejections":report["rejected"],"indexer_errors":errors,
            "actionable":False,"simulation_verified":False,"mainnet_broadcast":False}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--pages",type=int,default=3)
    parser.add_argument("--limit",type=int,default=60)
    parser.add_argument("--pace-seconds",type=float,default=7)
    parser.add_argument("--output",default="")
    args=parser.parse_args()
    report=scan(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),
                args.pages,args.limit,args.pace_seconds)
    print(json.dumps(report,indent=2))
    if args.output:
        with open(args.output,"w") as f:json.dump(report,f,indent=2)

if __name__=="__main__":main()
