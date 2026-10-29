"""Six-venue discovery -> graph -> native quote -> offline signed research.

Integrates existing original-account authenticators, source fixture exporter,
native quote adapters and signed Surfpool/rollback auditor. DBC and AMM v4 are
deliberately outside the current six-venue platform scope. This is a RESEARCH
pipeline, never a live execution engine or a profitability approval.
"""
import argparse
import json
import os
from pathlib import Path

from arb.next_ten_fork_pool_probe import probe, PROGRAMS
from arb.opportunity_graph import cycles
from arb.pumpswap_local_simulation import local_rpc_only

VENUES=("orca","raydium_cpmm","meteora_damm_v2",
        "pumpswap","meteora_dlmm","raydium_clmm")
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
MAX_CYCLES=500


def authenticated_graph(readiness, *, max_cycles=200):
    if type(max_cycles)is not int or not 1<=max_cycles<=MAX_CYCLES:
        raise ValueError("six-venue graph cycle limit invalid")
    if (not isinstance(readiness,dict) or
            readiness.get("source")!="READ_ONLY_MAINNET_BACKED_SURFPOOL" or
            any(readiness.get(k) is not False for k in SAFE)):
        raise ValueError("authenticated read-only Surfpool source required")
    by_venue=readiness.get("authenticated_pools")
    if not isinstance(by_venue,dict) or set(by_venue)!=set(VENUES):
        raise ValueError("exactly six authenticated venues required")
    pools=[]
    for venue in VENUES:
        entries=by_venue[venue]
        if not isinstance(entries,list) or len(entries)>12:
            raise ValueError("unbounded six-venue source inventory")
        for row in entries:
            if (not isinstance(row,dict) or row.get("venue")!=venue or
                    row.get("authenticated") is not True or
                    any(row.get(k) is not False for k in SAFE) or
                    type(row.get("slot")) is not int or row["slot"]<0 or
                    not isinstance(row.get("pool"),str) or not row["pool"]):
                raise ValueError("untrusted six-venue source identity")
            mints=row.get("mints")
            if (not isinstance(mints,list) or len(mints)!=2 or
                    any(not isinstance(m,str) or not m for m in mints) or
                    mints[0]==mints[1]):
                raise ValueError("untrusted token graph edge")
            pools.append({"venue":venue,"address":row["pool"],
                          "mints":mints,"verified":True,"slot":row["slot"]})
    # A bounded graph is a candidate inventory, never a tradable route.
    found=cycles(pools,max_hops=6,min_hops=2,
                 max_cycles=max_cycles+1,truncate=True) if pools else []
    routes=[{"start_mint":r["start_mint"],"hops":r["hops"],
             "legs":r["legs"],"quote_status":"NOT_QUOTED",
             "signed_simulation_status":"NOT_ATTEMPTED",**SAFE}
            for r in found[:max_cycles]]
    return {"status":"SIX_VENUE_AUTHENTICATED_GRAPH_ONLY",
            "venues":list(VENUES),
            "source_pool_count":len(pools),
            "venue_pool_counts":{v:len(by_venue[v]) for v in VENUES},
            "candidate_cycles":len(routes),
            "cycle_inventory_truncated":len(found)>max_cycles,
            "routes":routes,**SAFE}


def research(rpc, registry, fixture_dir, signed_dir, *, amount_in,
             observed_unix, maximum=12, max_cycles=200):
    """Only a local offline fork may run this integrated five-stage pipeline.

    The source quote ranking is indicative; signed results remain separate
    and a missing cost/conversion proof never becomes a profitable signal.
    """
    local_rpc_only(rpc)
    if os.environ.get("SURFPOOL_EXPLICITLY_OFFLINE")!="1":
        raise ValueError("explicit isolated Surfpool research opt-in required")
    if (type(amount_in)is not int or not 0<amount_in<2**64 or
            type(observed_unix)is not int or observed_unix<0 or
            type(maximum)is not int or not 1<=maximum<=12 or
            not isinstance(registry,dict)):
        raise ValueError("bounded offline research inputs required")
    if not set(VENUES)<=set(PROGRAMS):
        raise ValueError("six venue source adapters unavailable")
    from arb.m5_distinct_venue_coverage_batch import source_batch,offline_batch
    from arb.m5_source_triangle_quote_ranking import rank
    source_root=Path(fixture_dir)
    signed_root=Path(signed_dir)
    if source_root.resolve()==signed_root.resolve():
        raise ValueError("source and signed evidence directories must differ")
    batch=tuple((a,b) for a in VENUES for b in VENUES if a!=b)
    readiness=probe(rpc,registry,batch=batch)
    if set(readiness.get("authenticated_pools",{}))!=set(VENUES):
        raise ValueError("source adapter returned unexpected venue coverage")
    graph=authenticated_graph(readiness,max_cycles=max_cycles)
    source=source_batch(rpc,readiness,source_root,maximum=maximum)
    fixtures=[];indices=[]
    for row in source["routes"]:
        if row.get("status")=="AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE":
            fixture=json.loads((source_root/row["fixture"]).read_text())
            if (set(fixture.get("route_venues",[]))-set(VENUES)):
                raise ValueError("source fixture contains out-of-scope venue")
            fixtures.append(fixture)
            indices.append(row["index"])
    ranking=rank(fixtures,amount_in=amount_in,observed_unix=observed_unix,
                 maximum=maximum)
    selected=[indices[r["index"]] for r in ranking["ranked"]
              if r.get("positive_gross") is True]
    # The existing signed coordinator enforces Ed25519, CPI amount continuity
    # and negative rollback proof. Never mark a result actionable here.
    signed=offline_batch(rpc,source_root,signed_root,
                         observed_unix=observed_unix,route_indices=selected)
    return {"status":"SIX_VENUE_OFFLINE_DISCOVERY_TO_SIMULATION_RESEARCH",
            "venue_count":len(VENUES),"venues":list(VENUES),
            "discovery":{"authenticated_pools":graph["source_pool_count"],
                         "failed_pool_checks":len(readiness.get("failed_pool_checks",[]))},
            "graph":{"candidate_cycles":graph["candidate_cycles"],
                     "truncated":graph["cycle_inventory_truncated"]},
            "quote":{"source_fixtures_exported":source["exported"],
                     "fully_quoted":ranking["fully_quoted"],
                     "blocked":ranking["blocked"],
                     "gross_positive":ranking["positive_gross"],
                     "net_profitable_confirmed":0,
                     "fee_conversion_verified":False},
            "simulation":{"selected_positive_gross_routes":len(selected),
                          "signed_attempted":signed["attempted"],
                          "independent_signed_accepted":signed["independent_signed_accepted"],
                          "signed_quote_exact_matches":signed.get(
                              "observed_venue_quote_exact_matches",0)},
            "graph_artifact":graph,
            "ranking_artifact":ranking,
            "signed_artifact":signed,
            "reason":"historical or fork simulation is not live executable profit",
            **SAFE}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpc",default="http://127.0.0.1:8899")
    parser.add_argument("--registry",default="arb/pool_registry.json")
    parser.add_argument("--source-dir",required=True)
    parser.add_argument("--signed-dir",required=True)
    parser.add_argument("--amount-in",type=int,required=True)
    parser.add_argument("--observed-unix",type=int,required=True)
    parser.add_argument("--maximum",type=int,default=12)
    parser.add_argument("--max-cycles",type=int,default=200)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    report=research(args.rpc,json.loads(Path(args.registry).read_text()),
                    args.source_dir,args.signed_dir,amount_in=args.amount_in,
                    observed_unix=args.observed_unix,maximum=args.maximum,
                    max_cycles=args.max_cycles)
    Path(args.output).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({key:report[key] for key in (
        "status","venue_count","discovery","graph","quote","simulation","broadcast")}))


if __name__=="__main__":
    main()
