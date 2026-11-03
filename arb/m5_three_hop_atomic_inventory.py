"""Bounded empirical graph-selected three-hop build and simulate inventory.

Source phase on read-only upstream fork; offline phase after destroying source
fork. Never mark a discovered edge as a signed packet or simulated swap.
"""
import argparse
import json
from pathlib import Path

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def choose_pool_diverse_candidate(queue, selected_identities, used_pools, *, window=256):
    """Pick a fresh route maximizing pool coverage within a bounded queue window.

    Retain start-token round robin; do not treat candidate discovery as execution.
    """
    eligible=[(i,identity,route) for i,(identity,route) in enumerate(queue)
              if identity not in selected_identities]
    if not eligible:
        return None
    # Look past the lexicographically earliest 3-hop combinations, which can
    # repeatedly sample the same large pool cluster.
    def score(item):
        index,identity,route=item
        pools={(leg["venue"],leg["pool"]) for leg in route["legs"]}
        return (len(pools-used_pools),len(pools),-index)
    position,identity,route=max(eligible[:window],key=score)
    del queue[position]
    return identity,route

def failed_instruction_context(row, error):
    """Identify the failed top-level swap leg without guessing a DEX error meaning."""
    import re
    if not isinstance(error,str):
        return {}
    match=re.search(r"InstructionError.*?\[\s*(\d+)\s*,\s*\{.*?Custom.*?:\s*(\d+)\s*\}",error)
    if not match:
        return {}
    index,code=map(int,match.groups())
    venues=row.get("venues",[])
    pools=row.get("pools",[])
    if index>=len(venues) or index>=len(pools):
        return {"failed_instruction_index":index,"program_error_code":code}
    result={"failed_instruction_index":index,"program_error_code":code,
            "failed_venue":venues[index],"failed_pool":pools[index]}
    if venues[index]=="meteora_dlmm" and code==6042:
        result["program_error_name"]="PoolDisabled"
        result["diagnostic_class"]="DLMM_SWAP_BLOCKED_BY_POOL_STATUS_OR_ACTIVATION"
    elif venues[index]=="raydium_clmm" and code==6024:
        result["program_error_name"]="InvalidFirstTickArrayAccount"
        result["diagnostic_class"]="CLMM_FIRST_INITIALIZED_TICK_ARRAY_MISMATCH"
    return result

def diversified_three_hop_graph(readiness, maximum=100):
    """Bounded round-robin across authenticated token cycles and pool identities."""
    from collections import defaultdict, deque
    from arb.m5_seven_venue_route_scan import analyze, ORDER, SAFE
    from arb.opportunity_graph import cycles
    if type(maximum)is not int or not 1<=maximum<=200:
        raise ValueError("invalid cycle budget")
    pools=[{"venue":v,"address":p["pool"],"mints":p["mints"],"verified":True}
           for v in ORDER for p in readiness["authenticated_pools"][v]]
    graph=analyze(readiness,max_cycles=100)
    # Keep rotations as alternative start-token choices for each genuine pool
    # cycle. Select one unique pool cycle per round-robin starting token.
    candidates=defaultdict(deque)
    seen_by_start=defaultdict(set)
    unique_identities=set()
    for anchor in sorted({m for p in pools for m in p["mints"]}):
        for route in cycles(pools,anchors=[anchor],min_hops=3,max_hops=3,
                            max_cycles=1000,truncate=True):
            legs=route["legs"]
            keys=tuple((x["venue"],x["pool"],x["input"]) for x in legs)
            identity=min(keys[i:]+keys[:i] for i in range(3))
            unique_identities.add(identity)
            if identity in seen_by_start[anchor]:
                continue
            seen_by_start[anchor].add(identity)
            candidates[anchor].append((identity,route))
    result=[]
    selected_identities=set()
    used_pools=set()
    starts=sorted(candidates)
    while starts and len(result)<maximum:
        next_starts=[]
        for start in starts:
            q=candidates[start]
            choice=choose_pool_diverse_candidate(q,selected_identities,used_pools)
            if choice is not None:
                identity,r=choice
                selected_identities.add(identity)
                used_pools.update((leg["venue"],leg["pool"]) for leg in r["legs"])
                result.append({"start_mint":r["start_mint"],"hops":3,
                    "legs":r["legs"],"venue_count":len(r["venues"]),
                    "quote_status":"NOT_QUOTED",
                    "signed_simulation_status":"NOT_ATTEMPTED",**SAFE})
            if any(identity not in selected_identities for identity,_ in q):
                next_starts.append(start)
            if len(result)>=maximum:
                break
        starts=next_starts
    if not result:
        raise ValueError("no authenticated triangles found")
    graph.update(routes=result,connected_cycles=len(result),
        cycle_budget=maximum,cycle_inventory_truncated=True,
        cycle_count_is_exhaustive=False,
        three_hop_candidate_identities_considered=len(unique_identities),
        three_hop_distinct_token_paths=len({tuple([r["start_mint"]]+[leg["output"] for leg in r["legs"][:2]]) for r in result}),
        three_hop_distinct_start_mints=len({r["start_mint"] for r in result}),
        three_hop_distinct_selected_pools=len(used_pools),
        three_hop_distinct_selected_venues=len({v for v,_ in used_pools}),
        three_hop_sample_policy="START_MINT_ROUND_ROBIN_POOL_COVERAGE_GREEDY_256_ROTATION_DEDUP",
        cycle_coverage_by_hops={"3":{"returned":len(result),
            "budget":maximum,"truncated":len(unique_identities)>len(result)}})
    return graph

def source_capture(rpc, graph, directory, *, shard_index=0, shard_count=1, target=None):
    from arb.m5_four_to_six_source_capture import capture
    root=Path(directory)
    root.mkdir(parents=True,exist_ok=True)
    if graph.get("status")!="SOURCE_AUTHENTICATED_ROUTE_DISCOVERY_ONLY":
        raise ValueError("authenticated graph required")
    rows=[]
    blocked=[]
    venue_cache={}
    selected=[(i,r) for i,r in enumerate(graph["routes"]) if r.get("hops")==3]
    if (type(shard_index)is not int or type(shard_count)is not int
            or shard_count<1 or not 0<=shard_index<shard_count):
        raise ValueError("invalid three-hop route shard")
    for j,(index,route) in enumerate(selected):
        if j % shard_count != shard_index:
            continue
        entry={"id":"3H-%02d"%(j+1),"graph_route_index":index,
               "mints":[route["start_mint"]]+[x["output"] for x in route["legs"]],
               "venues":[x["venue"] for x in route["legs"]],
               "pools":[x["pool"] for x in route["legs"]],
               "discovery_status":"AUTHENTICATED_CLOSED_CYCLE",
               "source_status":"NOT_CAPTURED",
               "atomic_build_status":"NOT_ATTEMPTED",
               "simulation_status":"NOT_ATTEMPTED",**SAFE}
        fixture=root/("source-%02d.json"%j)
        try:
            capture(rpc,graph,index,fixture,venue_cache=venue_cache)
            entry["source_status"]="CAPTURED"
            entry["fixture"]=fixture.name
        except (ValueError,KeyError,TypeError,RuntimeError,OSError) as exc:
            entry["source_status"]="CAPTURE_BLOCKED"
            entry["diagnostic"]=str(exc)[:300]
        if entry["source_status"]=="CAPTURED":
            rows.append(entry)
        else:
            blocked.append(entry)
        (root/"three-hop-inventory.json").write_text(json.dumps(
            {"status":"SOURCE_THREE_HOP_INVENTORY",
             "cycle_count":len(selected),"shard_index":shard_index,
             "shard_count":shard_count,"shard_cycle_count":len(rows),
             "attempted_source_captures":len(rows)+len(blocked),
             "blocked_source_routes":blocked,
             "cached_distinct_pool_directions":len(venue_cache),
            "three_hop_truncated":graph.get("cycle_coverage_by_hops",{}).get("3",{}).get("truncated"),
             "routes":rows,**SAFE},indent=2)+"\n")
        if shard_count==1 and target is not None and len(rows)>=target:
            break
    if shard_count==1 and target is not None and len(rows)<target:
        raise RuntimeError(f"only {len(rows)}/{target} source-capturable routes; {len(blocked)} blocked")
    return rows

def offline_simulate(rpc,directory,*,amount=100000,shard_index=0,shard_count=1):
    from arb.pumpswap_local_simulation import local_rpc_only
    from arb.next_ten_signed_atomic_offline import run_four_to_six_venue
    import os
    local_rpc_only(rpc)
    if os.environ.get("SURFPOOL_EXPLICITLY_OFFLINE")!="1" or os.environ.get("SURFPOOL_DATASOURCE_RPC_URL"):
        raise ValueError("source-disconnected explicit offline Surfpool required")
    if type(amount)is not int or not 0<amount<2**64:
        raise ValueError("positive u64 exact input required")
    root=Path(directory)
    report=json.loads((root/"three-hop-inventory.json").read_text())
    if (type(shard_index)is not int or type(shard_count)is not int
            or shard_count<1 or not 0<=shard_index<shard_count):
        raise ValueError("invalid offline route shard")
    report["routes"]=[row for j,row in enumerate(report["routes"])
                      if j % shard_count == shard_index]
    report["shard_index"]=shard_index
    report["shard_count"]=shard_count
    report["shard_cycle_count"]=len(report["routes"])
    for row in report["routes"]:
        if row["source_status"]!="CAPTURED":
            continue
        row["atomic_build_status"]="BUILD_ATTEMPTED_NO_SIGNED_PACKET"
        row["simulation_status"]="NOT_ATTEMPTED"
        try:
            fixture=json.loads((root/row["fixture"]).read_text())
            receipt=run_four_to_six_venue(rpc,fixture,amount_in=amount,
                                          ephemeral_source_registry=True)
            (root/("receipt-"+row["id"]+".json")).write_text(json.dumps(receipt,indent=2)+"\n")
            if receipt.get("signed_packet_crypto_bound") is True and receipt.get("signed_transaction_signature"):
                row["atomic_build_status"]="SIGNED_ATOMIC_PACKET_BUILT"
                row["signed_transaction_signature"]=receipt["signed_transaction_signature"]
                row["simulation_status"]=("SIGNED_SIMULATION_AND_ROLLBACK_VERIFIED"
                    if receipt.get("signed_atomic_simulation_verified") is True
                    and receipt.get("rollback_failure_case_verified") is True
                    else "SIGNED_SIMULATION_NOT_VERIFIED")
                row["simulation_detail"]=receipt.get("status")
                row["positive_error"]=receipt.get("positive_error")
                if receipt.get("positive_error") is not None:
                    row["positive_program_log_tail"]=[str(x)[:180] for x in
                        (receipt.get("positive_logs") or [])[-8:]]
                row.update(failed_instruction_context(row,str(receipt.get("positive_error"))))
                if row["simulation_status"]=="SIGNED_SIMULATION_NOT_VERIFIED":
                    row["diagnostic"]=json.dumps({
                        "receipt_status":receipt.get("status"),
                        "positive_error":receipt.get("positive_error"),
                        "signed_atomic_simulation_verified":receipt.get("signed_atomic_simulation_verified"),
                        "rollback_failure_case_verified":receipt.get("rollback_failure_case_verified"),
                    },sort_keys=True)[:500]
                row["compute_units"]=receipt.get("positive_units_consumed")
            else:
                row["atomic_build_status"]="NO_VERIFIABLE_SIGNED_PACKET"
                row["simulation_status"]="NOT_ATTEMPTED"
                row["diagnostic"]=receipt.get("status")
        except (ValueError,KeyError,TypeError,RuntimeError,OSError) as exc:
            row["diagnostic"]=type(exc).__name__+": "+str(exc)[:950]
            row.update(failed_instruction_context(row,str(exc)))
            row["simulation_status"]="NOT_ATTEMPTED_OR_ABORTED_DURING_PREPARATION"
        report["status"]="OFFLINE_THREE_HOP_ATOMIC_BUILD_AND_SIMULATION_INVENTORY"
        report["build_confirmed"]=sum(r["atomic_build_status"]=="SIGNED_ATOMIC_PACKET_BUILT" for r in report["routes"])
        report["simulations_verified"]=sum(r["simulation_status"]=="SIGNED_SIMULATION_AND_ROLLBACK_VERIFIED" for r in report["routes"])
        (root/"three-hop-inventory.json").write_text(json.dumps(report,indent=2)+"\n")
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--phase",choices=("source","offline"),required=True)
    p.add_argument("--rpc",default="http://127.0.0.1:8899")
    p.add_argument("--graph")
    p.add_argument("--directory",required=True)
    p.add_argument("--amount",type=int,default=100000)
    p.add_argument("--source-target",type=int,default=None)
    p.add_argument("--shard-index",type=int,default=0)
    p.add_argument("--shard-count",type=int,default=1)
    args=p.parse_args()
    if args.phase=="source":
        if not args.graph: p.error("--graph required for source")
        result=source_capture(args.rpc,json.loads(Path(args.graph).read_text()),args.directory,
                              shard_index=args.shard_index,shard_count=args.shard_count,target=args.source_target)
        print(json.dumps({"three_hop_capture_attempts":len(result),
                          "source_captured":sum(r["source_status"]=="CAPTURED" for r in result)}))
    else:
        r=offline_simulate(args.rpc,args.directory,amount=args.amount,
                           shard_index=args.shard_index,shard_count=args.shard_count)
        print(json.dumps({"cycle_count":r["cycle_count"],
                          "signed_builds":r.get("build_confirmed",0),
                          "verified_simulations":r.get("simulations_verified",0)}))

if __name__=="__main__":
    main()
