"""Long-running, read-only source-authenticated route coverage scanner.

Run against a locally managed *source-backed* Surfpool RPC; no RPC writes,
no trade broadcasts, no invented quotes or profitability. A process manager
must keep this service alive. This is NOT the offline signing verifier.
"""
import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from arb.pumpswap_local_simulation import local_rpc_only

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}


def scan_once(rpc,registry,*,candidate_budget=200,target_unique_starts=200,
              source_probe=None,route_builder=None):
    """Separate authenticated topology coverage from executable/quoted starts."""
    from arb.m5_seven_venue_route_scan import ORDER
    from arb.m5_three_hop_atomic_inventory import diversified_three_hop_graph
    from arb.m5_start_mint_expansion import topology
    from arb.next_ten_fork_pool_probe import probe
    local_rpc_only(rpc)
    if not isinstance(registry,dict) or not isinstance(registry.get("pools"),list):
        raise ValueError("pool registry required")
    if (type(candidate_budget)is not int or not 1<=candidate_budget<=200 or
            type(target_unique_starts)is not int or not 1<=target_unique_starts<=100000):
        raise ValueError("invalid discovery limits")
    # The source-backed probe authenticates program owner, token identity,
    # vault state and slot. Registry records alone have NO evidence status.
    source_probe=source_probe or probe
    readiness=source_probe(rpc,registry,
        batch=tuple((a,b) for a in ORDER for b in ORDER if a!=b),
        maximum_per_venue=48,require_dlmm_swap_eligible=True,
        prefer_start_mint_coverage=True)
    if (not isinstance(readiness,dict) or
            readiness.get("source")!="READ_ONLY_MAINNET_BACKED_SURFPOOL" or
            any(readiness.get(key) is not False for key in SAFE)):
        raise ValueError("source-authenticated safety evidence unavailable")
    verified=readiness.get("authenticated_pools")
    if not isinstance(verified,dict) or set(verified)!=set(ORDER):
        raise ValueError("incomplete authenticated venue coverage")
    pools=[]
    for venue in ORDER:
        if not isinstance(verified[venue],list):
            raise ValueError("invalid source venue pool list")
        for p in verified[venue]:
            if (not isinstance(p,dict) or p.get("authenticated") is not True
                    or p.get("venue")!=venue or
                    type(p.get("slot")) is not int or p["slot"]<0 or
                    any(p.get(key) is not False for key in SAFE) or
                    not isinstance(p.get("pool"),str) or not p["pool"] or
                    not isinstance(p.get("mints"),list) or len(p["mints"])!=2):
                raise ValueError("untrusted source pool row")
            pools.append({"venue":venue,"address":p["pool"],
                          "mints":p["mints"]})
    topology_evidence=topology(pools) if pools else {"three_hop_start_mint_count":0,
                                                      "three_hop_start_mints":[]}
    route_builder=route_builder or diversified_three_hop_graph
    graph=route_builder(readiness,maximum=candidate_budget,
                        allow_start_rotations=True)
    if (graph.get("status")!="SOURCE_AUTHENTICATED_ROUTE_DISCOVERY_ONLY"
            or any(graph.get(key) is not False for key in SAFE)):
        raise ValueError("source graph did not pass safety contract")
    selected={r["start_mint"] for r in graph["routes"] if r.get("hops")==3}
    authenticated=set(topology_evidence["three_hop_start_mints"])
    if not selected.issubset(authenticated):
        raise ValueError("graph start not independently source-authenticated")
    return {
        "status":"READ_ONLY_COVERAGE_SCAN_NOT_PROFITABILITY_VERIFIED",
        "observed_at":datetime.now(timezone.utc).isoformat(),
        "target_unique_start_mints":target_unique_starts,
        "source_authenticated_pool_count":len(pools),
        "source_topology_unique_start_mints":len(authenticated),
        "selected_graph_unique_start_mints":len(selected),
        "selected_three_hop_candidate_routes":sum(
            r.get("hops")==3 for r in graph["routes"]),
        "candidate_route_budget":candidate_budget,
        "candidate_graph_truncated":graph.get("cycle_coverage_by_hops",{})
            .get("3",{}).get("truncated"),
        "target_met_on_topology":len(authenticated)>=target_unique_starts,
        "target_met_on_verified_execution":False,
        "source_captured_start_mints":None,
        "signed_rollback_verified_start_mints":None,
        "quoted_routes":0,
        "profitable_routes":None,
        "profitability_status":"NOT_EVALUATED",
        "continuous_scan_service":True,
        **SAFE,
    }


def write_snapshot(directory,result):
    root=Path(directory)
    root.mkdir(parents=True,exist_ok=True)
    # Replace the latest view atomically; retain append-only history.
    payload=json.dumps(result,sort_keys=True)+"\n"
    tmp=root/("latest.json.tmp."+str(os.getpid()))
    try:
        tmp.write_text(payload,encoding="utf-8")
        os.replace(tmp,root/"latest.json")
    finally:
        if tmp.exists():
            tmp.unlink()
    with (root/"history.jsonl").open("a",encoding="utf-8") as log:
        log.write(payload)


def run(rpc,registry,directory,*,interval_seconds=60,max_scans=0,
        candidate_budget=200,target_unique_starts=200,
        sleeper=time.sleep,scan=scan_once):
    local_rpc_only(rpc)
    if (type(interval_seconds) not in (int,float) or
            not 1<=interval_seconds<=3600 or
            type(max_scans)is not int or max_scans<0):
        raise ValueError("invalid scanner schedule")
    n=0
    while max_scans==0 or n<max_scans:
        n+=1
        try:
            report=scan(rpc,registry,candidate_budget=candidate_budget,
                        target_unique_starts=target_unique_starts)
        except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:
            # An authentication/RPC failure is explicit and cannot inherit
            # yesterday's coverage as a fresh valid scan.
            report={"status":"SOURCE_SCAN_FAILED",
                    "observed_at":datetime.now(timezone.utc).isoformat(),
                    "error_class":type(exc).__name__,
                    "diagnostic":str(exc)[:320],
                    "target_met_on_verified_execution":False,
                    "profitable_routes":None,
                    "profitability_status":"NOT_EVALUATED",**SAFE}
        write_snapshot(directory,report)
        print(json.dumps(report,sort_keys=True),flush=True)
        if max_scans==0 or n<max_scans:
            sleeper(interval_seconds)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--rpc",default="http://127.0.0.1:8899")
    parser.add_argument("--registry",default="arb/pool_registry.json")
    parser.add_argument("--output",default="scan-results")
    parser.add_argument("--interval-seconds",type=float,default=60)
    parser.add_argument("--max-scans",type=int,default=0,
                        help="0 means continuous until the process is stopped")
    parser.add_argument("--candidate-budget",type=int,default=200)
    parser.add_argument("--target-unique-starts",type=int,default=200)
    args=parser.parse_args()
    with open(args.registry,encoding="utf-8") as source:
        registry=json.load(source)
    run(args.rpc,registry,args.output,interval_seconds=args.interval_seconds,
        max_scans=args.max_scans,candidate_budget=args.candidate_budget,
        target_unique_starts=args.target_unique_starts)


if __name__=="__main__":
    main()
