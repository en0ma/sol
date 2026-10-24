"""Bounded external pool-ID discovery; candidates are never trusted as verified.

An indexer provides addresses ONLY. Pool owner, mints, reserves and fees must
be independently checked by arb.pool_registry.refresh against Solana RPC.
"""
import json
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from arb.onchain_pool_discovery import VENUES

ENDPOINTS={"meteora_dlmm":"https://dlmm.datapi.meteora.ag/pools",
           "meteora_damm_v2":"https://damm-v2.datapi.meteora.ag/pools"}
BASE58=set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")

def _valid_address(address):
    return isinstance(address,str) and 32<=len(address)<=44 and all(c in BASE58 for c in address)

def extract_meteora_candidates(venue,payload):
    if venue not in ENDPOINTS:raise ValueError("unsupported indexer venue")
    if isinstance(payload,list):
        rows=payload
    elif isinstance(payload,dict):
        rows=next((payload[k] for k in ("data","pools","items")
                   if isinstance(payload.get(k),list)),None)
        if rows is None:raise ValueError("unknown indexed pool response layout")
    else:
        raise ValueError("invalid indexed pool response")
    if len(rows)>1000:raise ValueError("oversize indexer response")
    result=[];seen=set()
    for row in rows:
        if not isinstance(row,dict):continue
        address=next((row[k] for k in ("address","pool_address","poolAddress","pubkey")
                      if _valid_address(row.get(k))),None)
        if not address or address in seen:continue
        seen.add(address)
        result.append({"venue":venue,"address":address,
                       "discovery_source":"meteora_indexer",
                       "verified":False,"actionable":False})
    return result

def fetch_candidates(venue,page=1,page_size=100,timeout=20):
    if venue not in ENDPOINTS or type(page)is not int or not 1<=page<=10000:
        raise ValueError("invalid venue/page")
    if type(page_size)is not int or not 1<=page_size<=100:
        raise ValueError("invalid page size")
    url=ENDPOINTS[venue]+"?"+urlencode({"page":page,"page_size":page_size})
    with urlopen(Request(url,headers={"Accept":"application/json",
                                     "User-Agent":"sol-pool-candidate-discovery/1"}),
                 timeout=timeout) as response:
        payload=json.load(response)
    return extract_meteora_candidates(venue,payload)

def discover_and_validate(rpc,venue,page=1,page_size=100):
    from arb.pool_registry import refresh
    candidates=fetch_candidates(venue,page,page_size)
    checked=refresh(rpc,candidates[:min(len(candidates),200)])
    return {"venue":venue,"indexer_candidate_count":len(candidates),
            "onchain_verified_count":checked["verified_count"],
            "onchain_rejected_count":checked["rejected_count"],
            "verified_pool_identities":[{"venue":p["venue"],"address":p["address"],
                                         "mints":p["mints"]} for p in checked["verified_pools"]],
            "rejections":checked["rejected"],
            "quotes_verified":False,"swap_simulation_verified":False,
            "mainnet_broadcast":False}

def main():
    import argparse,os
    parser=argparse.ArgumentParser()
    parser.add_argument("--venue",choices=sorted(ENDPOINTS),required=True)
    parser.add_argument("--page",type=int,default=1)
    parser.add_argument("--page-size",type=int,default=20)
    parser.add_argument("--output",default="")
    args=parser.parse_args()
    report=discover_and_validate(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),
                                 args.venue,args.page,args.page_size)
    print(json.dumps(report,indent=2))
    if args.output:
        with open(args.output,"w") as f:json.dump(report,f,indent=2)

if __name__=="__main__":main()
