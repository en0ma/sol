"""Safely ingest on-chain discovery identities into the persistent pool registry.

Discovered JSON is untrusted until each candidate is freshly verified by RPC.
Never replace stored identities from incomplete discovery, never write a
partial refresh, and never interpret a discovered pair as executable profit.
"""
import argparse,json,os
from pathlib import Path
from arb.pool_registry import refresh
from arb.onchain_pool_discovery import VENUES

def merge_identities(existing,discovery,max_new=50):
    if not isinstance(existing,list) or not isinstance(discovery,dict):
        raise ValueError("invalid registry or discovery report")
    pools=discovery.get("pools")
    if not isinstance(pools,list) or len(pools)>200 or len(existing)>200:
        raise ValueError("unbounded discovery report")
    merged=[];seen=set();new=0
    for p in existing:
        venue,address=p.get("venue"),p.get("address")
        if venue not in VENUES or not isinstance(address,str):
            raise ValueError("invalid existing registry entry")
        if (venue,address) in seen:continue
        merged.append({"venue":venue,"address":address,**(
            {"mints":p["mints"]} if "mints" in p else {})})
        seen.add((venue,address))
    for p in pools:
        venue,address=p.get("venue"),p.get("address")
        if venue not in VENUES or not isinstance(address,str) or not 32<=len(address)<=64:
            continue
        if (venue,address) in seen:continue
        if new>=max_new:break
        # Provisional mint hints only; refresh must recheck state and vaults.
        merged.append({"venue":venue,"address":address,**(
            {"mints":p["mints"]} if isinstance(p.get("mints"),list)
            and len(p["mints"])==2 else {})})
        seen.add((venue,address));new+=1
    return merged,new

def ingest(rpc,existing,discovery):
    merged,added=merge_identities(existing,discovery)
    verified=refresh(rpc,merged)
    # Existing verified pool identities are retained as hints, but any
    # rejected candidate is excluded from the output registry.
    eligible=[{"venue":p["venue"],"address":p["address"],"mints":p["mints"]}
              for p in verified["verified_pools"]]
    return {"added_candidates":added,"verified_count":len(eligible),
            "rejected_count":verified["rejected_count"],
            "registry":{"pools":eligible},
            "report":verified,"broadcast":False}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--registry",default="arb/pool_registry.json")
    parser.add_argument("--discovery",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    current=json.loads(Path(args.registry).read_text())["pools"]
    discovered=json.loads(Path(args.discovery).read_text())
    result=ingest(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),
                  current,discovered)
    # Only publish a new registry snapshot if all retained identities passed
    # fresh validation, so an API outage cannot erase previous state.
    if result["rejected_count"]:
        print(json.dumps({"status":"PARTIAL","rejected":result["report"]["rejected"],
                          "registry_updated":False},indent=2))
        return 2
    Path(args.output).write_text(json.dumps(result["registry"],indent=2)+"\n")
    print(json.dumps({"status":"PASS","new_candidates":result["added_candidates"],
        "verified_count":result["verified_count"],"registry_updated":True},indent=2))
    return 0
if __name__=="__main__":raise SystemExit(main())
