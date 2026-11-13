"""Read-only Raydium CLMM pool/tick readiness diagnostic on Surfpool.

Uses pinned identity hints, not unfiltered program scans. No swap approval.
"""
import json,os
from arb.pool_registry import refresh
from arb.raydium_clmm_ticks import inspect

def report(rpc,entries):
    candidates=[e for e in entries if e.get("venue")=="raydium_clmm"]
    output={"status":"NOT_CONFIGURED" if not candidates else "PARTIAL",
            "candidates":len(candidates),"verified_pools":0,
            "tick_ready_directions":0,"results":[],"swap_executed":False}
    for item in candidates[:8]:
        base=refresh(rpc,[item])
        if base["verified_count"]!=1:
            output["results"].append({"address":item["address"],"status":"POOL_INVALID",
                                      "rejected":base["rejected"]})
            continue
        output["verified_pools"]+=1
        dirs={}
        for zero,name in ((True,"zero_for_one"),(False,"one_for_zero")):
            try:
                result=inspect(rpc,item["address"],zero_for_one=zero)
                dirs[name]=result
                output["tick_ready_directions"]+=int(result["all_arrays_valid"])
            except Exception as exc:
                dirs[name]={"all_arrays_valid":False,"error":str(exc)[:200]}
        output["results"].append({"address":item["address"],
                                  "status":"INSPECTED","directions":dirs})
    if candidates:
        output["status"]="PASS" if output["verified_pools"]==len(candidates) and output["tick_ready_directions"] else "PARTIAL"
    return output

def main():
    with open("arb/pool_registry.json") as f:entries=json.load(f)["pools"]
    result=report(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),entries)
    print(json.dumps(result,indent=2))
    out=os.environ.get("CLMM_PREFLIGHT_REPORT")
    if out:
        with open(out,"w") as f:json.dump(result,f,indent=2)
    return 0 if result["status"] in ("PASS","NOT_CONFIGURED","PARTIAL") else 1
if __name__=="__main__":raise SystemExit(main())
