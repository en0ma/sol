"""Persistent pool identity registry refreshed from direct Solana JSON-RPC.

Stored entries are hints only. Every refresh revalidates owner, decoder,
mints and vault balances; stale/failed entries never enter route graph.
No unfiltered scans, DEX HTTP APIs or transaction broadcasting.
"""
import argparse,base64,json,os
from pathlib import Path
from arb.rpc import call
from arb.onchain_pool_discovery import VENUES,verify

def refresh(rpc,entries):
    valid=[];rejected=[]
    if not isinstance(entries,list) or len(entries)>200:
        raise ValueError("registry entries must be a bounded list")
    seen=set()
    for entry in entries:
        venue=entry.get("venue"); address=entry.get("address")
        if venue not in VENUES or not isinstance(address,str) or len(address)>64 or len(address)<32:
            rejected.append({"entry":entry,"reason":"INVALID_REGISTRY_ENTRY"});continue
        if (venue,address) in seen:
            rejected.append({"venue":venue,"address":address,"reason":"DUPLICATE"});continue
        seen.add((venue,address))
        program,_,_,_,decoder=VENUES[venue]
        try:
            response=call(rpc,"getAccountInfo",[address,{"encoding":"base64","commitment":"confirmed"}])
            info=response.get("value")
            if not info or info.get("owner")!=program or info.get("executable"):
                raise ValueError("pool missing or owner mismatch")
            raw=base64.b64decode(info["data"][0],validate=True)
            decoded=decoder(raw)
            verified=verify(rpc,venue,address,decoded)
            previous=entry.get("mints")
            if previous is not None and sorted(previous)!=sorted(verified["mints"]):
                raise ValueError("pool mint identity changed")
            if not isinstance(verified.get("slot"),int):
                raise ValueError("missing verification slot")
            valid.append({**verified,"verified":True})
        except Exception as exc:
            rejected.append({"venue":venue,"address":address,
                             "reason":type(exc).__name__+": "+str(exc)[:200]})
    graph={}
    for pool in valid:
        key=tuple(sorted(pool["mints"]))
        graph.setdefault(key,[]).append({"venue":pool["venue"],"address":pool["address"]})
    shared=[{"mints":list(pair),"pools":pools} for pair,pools in graph.items()
            if len({p["venue"] for p in pools})>1]
    coverage={name:{"validated_pools":sum(p["venue"]==name for p in valid),
                    "rejected_pools":sum(p.get("venue")==name for p in rejected)}
              for name in VENUES}
    return {"status":"COMPLETE" if not rejected else "PARTIAL",
            "venue_validation_coverage":coverage,
            "verified_count":len(valid),"rejected_count":len(rejected),
            "verified_pools":valid,"rejected":rejected,"shared_pairs":shared,
            "opportunities_executed":0,"broadcast":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--registry",default="arb/pool_registry.json")
    p.add_argument("--output",default=os.environ.get("POOL_REGISTRY_REPORT",""))
    args=p.parse_args()
    entries=json.loads(Path(args.registry).read_text())["pools"]
    report=refresh(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),entries)
    print(json.dumps(report,indent=2))
    if args.output:Path(args.output).write_text(json.dumps(report,indent=2))
    return 0 if report["status"]=="COMPLETE" and report["verified_count"]>0 else 1

if __name__=="__main__":raise SystemExit(main())
