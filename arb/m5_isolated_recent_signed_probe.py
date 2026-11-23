"""Isolated signed-evidence experiment for newly source-verified Meteora pools.

No new route affects the primary 140-route signed inventory. The source stage
builds a bounded candidate-only graph with independent source snapshots.
The offline stage is the existing signed atomic + rollback simulator.
"""
import json
from pathlib import Path
from arb.m5_start_mint_expansion import topology

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}


def select_isolated_routes(graph,control_starts,candidates,*,maximum=6):
    """Accept only authenticated 3-hop routes using a NEW source-probed pool."""
    if (not isinstance(graph,dict)
            or graph.get("status")!="SOURCE_AUTHENTICATED_ROUTE_DISCOVERY_ONLY"
            or not isinstance(control_starts,(list,set,tuple))
            or not all(isinstance(x,str) for x in control_starts)
            or not isinstance(candidates,list)
            or type(maximum)is not int or not 1<=maximum<=12):
        raise ValueError("isolated authenticated graph and bounded selection required")
    ids={(row["venue"],row["address"]) for row in candidates
         if row.get("source_verified_only") is True}
    if len(ids)!=len(candidates):
        raise ValueError("source-verified candidate identity required")
    old=set(control_starts)
    seen=set()
    selected=[]
    for row in graph.get("routes",[]):
        if (row.get("hops")!=3 or row.get("start_mint") in old
                or len(row.get("legs",[]))!=3
                or not any((leg.get("venue"),leg.get("pool")) in ids
                           for leg in row["legs"])):
            continue
        identity=(row["start_mint"],tuple(
            (leg["venue"],leg["pool"],leg["input"],leg["output"])
            for leg in row["legs"]))
        if identity in seen:
            continue
        seen.add(identity)
        selected.append(row)
        if len(selected)>=maximum:
            break
    out=dict(graph)
    out["routes"]=selected
    out["cycle_budget"]=maximum
    out["connected_cycles"]=len(selected)
    out["three_hop_distinct_start_mints"]=len({
        row["start_mint"] for row in selected})
    out["isolated_recent_candidate_only"]=True
    out["baseline_control_unchanged"]=True
    out.update(SAFE)
    return out


def source_prepare(rpc,baseline_entries,candidates,directory,*,maximum=6):
    """Read-only source capture: only triangles involving recent pool identities."""
    from arb.next_ten_fork_pool_probe import probe
    from arb.m5_seven_venue_route_scan import ORDER
    from arb.m5_three_hop_atomic_inventory import (
        diversified_three_hop_graph,source_capture)
    root=Path(directory)
    root.mkdir(parents=True,exist_ok=True)
    if (not isinstance(baseline_entries,list) or
            not isinstance(candidates,list) or len(candidates)>24):
        raise ValueError("bounded isolated pool inputs required")
    old=topology(baseline_entries)
    old_starts=set(old["three_hop_start_mints"])
    all_rows=list(baseline_entries)+list(candidates)
    after=topology(all_rows)
    new_starts=set(after["three_hop_start_mints"])-old_starts
    candidate_ids={(c["venue"],c["address"]) for c in candidates}
    if not new_starts:
        return {"status":"NO_NEW_SOURCE_TOPOLOGY","selected_routes":0,
                "captured_routes":0,"candidate_new_starts":0,**SAFE}
    pairs={}
    for entry in all_rows:
        pairs.setdefault(frozenset(entry["mints"]),[]).append(entry)
    adjacency=after["mint_neighbors"]
    chosen={}
    for candidate in candidates:
        a,b=candidate["mints"]
        for c in set(adjacency.get(a,())) & set(adjacency.get(b,())):
            if not ({a,b,c}&new_starts):
                continue
            for edge in ((a,b),(a,c),(b,c)):
                # Preserve all recent candidates and a bounded assortment
                # of independent existing edge identities for source retry.
                for pool in pairs.get(frozenset(edge),[])[:4]:
                    chosen[(pool["venue"],pool["address"])]=pool
    for candidate in candidates:
        chosen[(candidate["venue"],candidate["address"])]=candidate
    # Prevent the supplemental experiment from exhausting the main
    # source-fork budget. All rows are reauthenticated by probe().
    if len(chosen)>80:
        raise ValueError("isolated candidate triangle exceeds 80 pool hints")
    from arb.pumpswap_local_simulation import local_rpc_only
    local_rpc_only(rpc)
    registry={"pools":list(chosen.values())}
    readiness=probe(rpc,registry,
        batch=tuple((a,b) for a in ORDER for b in ORDER if a!=b),
        maximum_per_venue=24,require_dlmm_swap_eligible=True)
    try:
        graph=diversified_three_hop_graph(
            readiness,maximum=24,allow_start_rotations=True)
    except ValueError as exc:
        if "no authenticated triangles" not in str(exc):
            raise
        return {"status":"NO_SOURCE_AUTHENTICATED_CANDIDATE_ROUTES",
                "selected_routes":0,"captured_routes":0,
                "candidate_new_starts":len(new_starts),**SAFE}
    isolated=select_isolated_routes(graph,old_starts,candidates,
                                   maximum=maximum)
    if not isolated["routes"]:
        return {"status":"NO_SOURCE_AUTHENTICATED_CANDIDATE_ROUTES",
                "selected_routes":0,"captured_routes":0,
                "candidate_new_starts":len(new_starts),**SAFE}
    (root/"graph.json").write_text(json.dumps(isolated,indent=2)+"\\n")
    source_capture(rpc,isolated,root)
    report=json.loads((root/"three-hop-inventory.json").read_text())
    return {"status":"ISOLATED_RECENT_SOURCE_CAPTURE_COMPLETED",
        "candidate_new_starts":len(new_starts),
        "selected_routes":len(isolated["routes"]),
        "captured_routes":len(report["routes"]),
        "captured_starts":report["source_captured_start_mints"],
        "source_capture_attempts":report["attempted_source_captures"],
        "baseline_control_unchanged":True,**SAFE}


def signed_summary(directory,control_starts):
    """Require independent cryptographic, simulation AND rollback receipt."""
    root=Path(directory)
    report=json.loads((root/"three-hop-inventory.json").read_text())
    verified=set()
    proof_routes=0
    for row in report["routes"]:
        if (row.get("source_status")!="CAPTURED"
                or row.get("atomic_build_status")!="SIGNED_ATOMIC_PACKET_BUILT"
                or row.get("simulation_status")!="SIGNED_SIMULATION_AND_ROLLBACK_VERIFIED"
                or not row.get("signed_transaction_signature")):
            continue
        receipt_path=root/("receipt-"+row["id"]+".json")
        if not receipt_path.is_file():
            continue
        receipt=json.loads(receipt_path.read_text())
        if (receipt.get("signed_packet_crypto_bound") is not True
                or not receipt.get("signed_transaction_signature")
                or receipt["signed_transaction_signature"]!=row["signed_transaction_signature"]
                or receipt.get("signed_atomic_simulation_verified") is not True
                or receipt.get("rollback_failure_case_verified") is not True):
            continue
        proof_routes+=1
        mint=row["mints"][0]
        if mint not in control_starts:
            verified.add(mint)
    return {"status":"ISOLATED_RECENT_SIGNED_ROLLBACK_AUDIT",
        "attempted":len(report["routes"]),
        "signed_and_rollback_verified_routes":proof_routes,
        "additional_distinct_verified_start_mints":len(verified),
        "additional_verified_start_mints":sorted(verified),
        "excluded_from_primary_inventory":True,**SAFE}
