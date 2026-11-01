"""Bounded empirical graph-selected three-hop build and simulate inventory.

Source phase on read-only upstream fork; offline phase after destroying source
fork. Never mark a discovered edge as a signed packet or simulated swap.
"""
import argparse
import json
from pathlib import Path

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def source_capture(rpc, graph, directory, *, shard_index=0, shard_count=1):
    from arb.m5_four_to_six_source_capture import capture
    root=Path(directory)
    root.mkdir(parents=True,exist_ok=True)
    if graph.get("status")!="SOURCE_AUTHENTICATED_ROUTE_DISCOVERY_ONLY":
        raise ValueError("authenticated graph required")
    rows=[]
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
        rows.append(entry)
        (root/"three-hop-inventory.json").write_text(json.dumps(
            {"status":"SOURCE_THREE_HOP_INVENTORY",
             "cycle_count":len(selected),"shard_index":shard_index,
             "shard_count":shard_count,"shard_cycle_count":len(rows),
             "attempted_source_captures":len(rows),
             "cached_distinct_pool_directions":len(venue_cache),
            "three_hop_truncated":graph.get("cycle_coverage_by_hops",{}).get("3",{}).get("truncated"),
             "routes":rows,**SAFE},indent=2)+"\n")
    return rows

def offline_simulate(rpc,directory,*,amount=100000):
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
                row["compute_units"]=receipt.get("positive_units_consumed")
            else:
                row["atomic_build_status"]="NO_VERIFIABLE_SIGNED_PACKET"
                row["simulation_status"]="NOT_ATTEMPTED"
                row["diagnostic"]=receipt.get("status")
        except (ValueError,KeyError,TypeError,RuntimeError,OSError) as exc:
            row["diagnostic"]=type(exc).__name__+": "+str(exc)[:300]
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
    p.add_argument("--shard-index",type=int,default=0)
    p.add_argument("--shard-count",type=int,default=1)
    args=p.parse_args()
    if args.phase=="source":
        if not args.graph: p.error("--graph required for source")
        result=source_capture(args.rpc,json.loads(Path(args.graph).read_text()),args.directory,
                              shard_index=args.shard_index,shard_count=args.shard_count)
        print(json.dumps({"three_hop_capture_attempts":len(result),
                          "source_captured":sum(r["source_status"]=="CAPTURED" for r in result)}))
    else:
        r=offline_simulate(args.rpc,args.directory,amount=args.amount)
        print(json.dumps({"cycle_count":r["cycle_count"],
                          "signed_builds":r.get("build_confirmed",0),
                          "verified_simulations":r.get("simulations_verified",0)}))

if __name__=="__main__":
    main()
