"""Topology-driven, read-only bridge-pool scouting for 40 distinct start mints.

The registry is a source hint, not proof of executable liquidity. Suggestions
become candidate edges only after source-RPC program and reserve verification.
This scout never signs, hydrates, trades, or marks routes profitable.
"""
import argparse,json
from collections import defaultdict
from pathlib import Path
from arb.onchain_pool_discovery import discover
from arb.orca_whirlpool import SOL,USDC

USDT="Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
HUBS=(SOL,USDC,USDT)
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
DEFAULT_VENUES=("orca","raydium_cpmm","meteora_damm_v2","raydium_clmm")

def topology(entries):
    if not isinstance(entries,list):
        raise ValueError("pool registry rows required")
    by_mint=defaultdict(list)
    seen=set()
    for p in entries:
        if not isinstance(p,dict):
            raise ValueError("malformed pool entry")
        venue,address,mints=p.get("venue"),p.get("address"),p.get("mints")
        if not isinstance(venue,str) or not isinstance(address,str) or not address or (
            not isinstance(mints,list) or len(mints)!=2 or
            any(not isinstance(m,str) or not m for m in mints) or mints[0]==mints[1]):
            raise ValueError("malformed pool identity")
        if (venue,address) in seen:
            raise ValueError("duplicate pool identity")
        seen.add((venue,address))
        for mint in mints:by_mint[mint].append(p)
    cyclic=set()
    for start,first_edges in by_mint.items():
        for a in first_edges:
            middle=a["mints"][0] if a["mints"][1]==start else a["mints"][1]
            for b in by_mint[middle]:
                if b["address"]==a["address"] and b["venue"]==a["venue"]:continue
                last=b["mints"][0] if b["mints"][1]==middle else b["mints"][1]
                if last==start or last==middle:continue
                for c in by_mint[last]:
                    if start not in c["mints"]:continue
                    ids={(x["venue"],x["address"]) for x in (a,b,c)}
                    if len(ids)==3:
                        cyclic.add(start)
                        break
                if start in cyclic:break
            if start in cyclic:break
    return {"distinct_mints":len(by_mint),"three_hop_start_mints":sorted(cyclic),
            "three_hop_start_mint_count":len(cyclic),
            "mint_neighbors":{m:sorted({p["mints"][0] if p["mints"][1]==m else p["mints"][1]
                for p in edges}) for m,edges in by_mint.items()}}

def bridge_targets(entries, *, maximum=36):
    if type(maximum)is not int or not 1<=maximum<=120:
        raise ValueError("bounded discovery target budget required")
    graph=topology(entries)
    existing=graph["three_hop_start_mints"]
    count=defaultdict(int)
    current_pairs=set()
    for p in entries:
        current_pairs.add(tuple(sorted(p["mints"])))
        for m in p["mints"]:count[m]+=1
    candidates=[]
    for mint,neighbors in graph["mint_neighbors"].items():
        if mint in existing or mint in HUBS or len(neighbors)!=1 or neighbors[0] not in HUBS:
            continue
        old=neighbors[0]
        for target in HUBS:
            if target==old or tuple(sorted((mint,target))) in current_pairs:
                continue
            # Hubs are already interconnected in the source registry.
            if tuple(sorted((old,target))) not in current_pairs:continue
            candidates.append({"mint":mint,"connected_hub":old,"missing_hub":target,
                               "pair":[mint,target],"current_pools":count[mint]})
    # Prefer established tokens with multiple authenticated pool identity hints.
    # Keep both missing-hub options adjacent; avoid 36 requests for one mint.
    candidates.sort(key=lambda x:(-x["current_pools"],x["mint"],x["missing_hub"]))
    result=[];selected=set()
    for row in candidates:
        if row["mint"] in selected:continue
        result.append(row)
        selected.add(row["mint"])
        if len(result)>=maximum:break
    return {"topology":graph,"targets":result,
            "targets_are_unverified_hints":True,**SAFE}

def scout(rpc,entries,*,maximum=36,venues=DEFAULT_VENUES):
    suggestions=bridge_targets(entries,maximum=maximum)
    pairs=[tuple(x["pair"]) for x in suggestions["targets"]]
    if not pairs:raise ValueError("no topology bridge suggestions")
    discovery=discover(rpc,pairs,venues=venues,limit=8)
    existing={(p["venue"],p["address"]) for p in entries}
    new=[{"venue":p["venue"],"address":p["address"],"mints":p["mints"],
          "source_verified_slot":p.get("slot"),"source_verified_only":True}
         for p in discovery["pools"] if (p["venue"],p["address"]) not in existing]
    merged=entries+new
    before=suggestions["topology"]
    after=topology(merged)
    return {"status":"READ_ONLY_TOPOLOGY_BRIDGE_SCOUT",
            "registered_pool_count":len(entries),"source_verified_new_pool_count":len(new),
            "source_verified_new_pools":new,"before_three_hop_start_mints":before["three_hop_start_mint_count"],
            "after_source_verified_topology_start_mints":after["three_hop_start_mint_count"],
            "additional_candidate_start_mints":sorted(set(after["three_hop_start_mints"])-
                set(before["three_hop_start_mints"])),
            "target_start_mints":40,"target_met_on_source_topology":after["three_hop_start_mint_count"]>=40,
            "target_met_on_signed_simulations":False,
            "searched_bridge_pairs":pairs,"source_search_venues":list(venues),
            "discovery_status":discovery["status"],"discovery_errors":discovery["errors"],
            "suggested_registry_pool_count":len(merged),
            **SAFE}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--registry",default="arb/pool_registry.json")
    p.add_argument("--output",required=True)
    p.add_argument("--rpc",default="http://127.0.0.1:8899")
    p.add_argument("--maximum",type=int,default=36)
    p.add_argument("--venues",default=",".join(DEFAULT_VENUES))
    a=p.parse_args()
    entries=json.loads(Path(a.registry).read_text())["pools"]
    result=scout(a.rpc,entries,maximum=a.maximum,venues=tuple(a.venues.split(",")))
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k not in
        ("source_verified_new_pools","discovery_errors","searched_bridge_pairs")}))
if __name__=="__main__":main()
