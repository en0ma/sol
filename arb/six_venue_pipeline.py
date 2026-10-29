"""Six-venue discovery -> graph -> native quote -> offline signed research.

Integrates existing original-account authenticators, source fixture exporter,
native quote adapters and signed Surfpool/rollback auditor. DBC and AMM v4 are
deliberately outside the current six-venue platform scope. This is a RESEARCH
pipeline, never a live execution engine or a profitability approval.
"""
import argparse
import hashlib
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
    identities=set()
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
            key=(venue,row["pool"])
            if key in identities:
                raise ValueError("duplicate authenticated pool identity")
            identities.add(key)
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



def source_research(rpc, registry, fixture_dir, *, amount_in,
                    observed_unix, maximum=12, max_cycles=200,
                    discovery_pairs=None):
    """Read-only source-backed Surfpool: authenticated pools -> ranked fixtures.

    This phase MUST complete and stop before a separate --offline Surfpool
    process executes signed simulations. Never sign against a source fork.
    """
    local_rpc_only(rpc)
    if (type(amount_in)is not int or not 0<amount_in<2**64 or
            type(observed_unix)is not int or observed_unix<0 or
            type(maximum)is not int or not 1<=maximum<=12 or
            not isinstance(registry,dict)):
        raise ValueError("bounded source research inputs required")
    if not set(VENUES)<=set(PROGRAMS):
        raise ValueError("six venue source adapters unavailable")
    from arb.m5_distinct_venue_coverage_batch import source_batch
    from arb.m5_source_triangle_quote_ranking import rank
    root=Path(fixture_dir)
    # Optional venue-owned direct getProgramAccounts search by explicit mint
    # pair. Every discovered address is reauthenticated by probe; no DEX
    # HTTP index hint or 'discovered == usable' shortcut is permitted.
    discovery={"status":"CURATED_REGISTRY_REAUTH_ONLY","verified":0,
               "rejected":0}
    if discovery_pairs is not None:
        from arb.onchain_pool_discovery import discover
        if (not isinstance(discovery_pairs,list) or
                not 1<=len(discovery_pairs)<=5 or
                any(not isinstance(pair,list) or len(pair)!=2 or
                    any(not isinstance(m,str) or not m for m in pair) or
                    pair[0]==pair[1] for pair in discovery_pairs)):
            raise ValueError("bounded explicit discovery mint pairs required")
        fresh=discover(rpc,discovery_pairs,limit=8,
                       registry_entries=registry.get("pools",[]),
                       venues=VENUES)
        # Never trust returned index metadata as proof. Probe rereads
        # program-owned pool accounts plus their actual vault balances.
        known={(p.get("venue"),p.get("address")) for p in registry.get("pools",[])
               if isinstance(p,dict)}
        incoming=[]
        for row in fresh["candidate_graph_pool_identities"]:
            if row["venue"] not in VENUES:
                raise ValueError("new candidate venue out of platform scope")
            key=(row["venue"],row["address"])
            if key not in known:
                incoming.append({"venue":row["venue"],"address":row["address"]})
                known.add(key)
        registry={**registry,"pools":[*incoming,*registry.get("pools",[])]}
        discovery={"status":fresh["status"],
                   "verified":fresh["candidate_graph_verified_count"],
                   "rejected":len(fresh["errors"]),
                   "new_identity_hints":len(incoming)}
    batch=tuple((a,b) for a in VENUES for b in VENUES if a!=b)
    readiness=probe(rpc,registry,batch=batch)
    if set(readiness.get("authenticated_pools",{}))!=set(VENUES):
        raise ValueError("unexpected source venue coverage")
    graph=authenticated_graph(readiness,max_cycles=max_cycles)
    source=source_batch(rpc,readiness,root,maximum=maximum)
    fixtures=[];indices=[];digests={}
    for row in source["routes"]:
        if row.get("status")=="AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE":
            path=(root/row["fixture"]).resolve()
            if path.parent!=root.resolve():
                raise ValueError("source fixture path escapes evidence directory")
            raw=path.read_bytes()
            fixture=json.loads(raw)
            if (not set(fixture.get("route_venues",[]))<=set(VENUES) or
                    len(fixture["route_venues"])!=3):
                raise ValueError("source fixture contains out-of-scope venue")
            fixtures.append(fixture)
            indices.append(row["index"])
            digests[row["fixture"]]=hashlib.sha256(raw).hexdigest()
    ranking=rank(fixtures,amount_in=amount_in,observed_unix=observed_unix,
                 maximum=maximum)
    selected=[indices[row["index"]] for row in ranking["ranked"]
              if row.get("positive_gross") is True]
    summary_raw=(root/"summary.json").read_bytes()
    ranking_raw=(json.dumps(ranking,sort_keys=True,separators=(",",":"))+"\\n").encode()
    (root/"six-venue-ranking.json").write_bytes(ranking_raw)
    manifest={"status":"SIX_VENUE_SIGNED_HANDOFF_UNEXECUTED",
              "venues":list(VENUES),"observed_unix":observed_unix,
              "amount_in":amount_in,"source_fixtures":digests,
              "source_summary_sha256":hashlib.sha256(summary_raw).hexdigest(),
              "source_ranking_sha256":hashlib.sha256(ranking_raw).hexdigest(),
              "selected_source_route_indices":selected,
              "selection_is_gross_only":True,
              "cost_conversion_verified":False,**SAFE}
    root.mkdir(parents=True,exist_ok=True)
    (root/"six-venue-handoff.json").write_text(json.dumps(manifest,indent=2)+"\n")
    return {"status":"SIX_VENUE_SOURCE_AND_QUOTE_RESEARCH",
            "discovery":{"venue_owned_search":discovery,
                         "authenticated_pools":graph["source_pool_count"],
                         "failed_pool_checks":len(readiness.get("failed_pool_checks",[]))},
            "graph":{"candidate_cycles":graph["candidate_cycles"],
                     "truncated":graph["cycle_inventory_truncated"]},
            "quote":{"source_fixtures_exported":source["exported"],
                     "fully_quoted":ranking["fully_quoted"],
                     "blocked":ranking["blocked"],
                     "gross_positive":ranking["positive_gross"],
                     "net_profitable_confirmed":0},
            "signed_simulation_status":"NOT_ATTEMPTED",
            "manifest":manifest,"graph_artifact":graph,
            "ranking_artifact":ranking,**SAFE}


def offline_research(rpc, fixture_dir, signed_dir):
    """Independent offline process consumes hash-bound source fixture handoff.

    Both the source-backed process and any RPC datasource must already be
    stopped. This entry point rejects absence of explicit offline opt-in.
    """
    local_rpc_only(rpc)
    if os.environ.get("SURFPOOL_EXPLICITLY_OFFLINE")!="1":
        raise ValueError("explicit isolated Surfpool offline opt-in required")
    src=Path(fixture_dir)
    dst=Path(signed_dir)
    if src.resolve()==dst.resolve():
        raise ValueError("source and signed evidence directories must differ")
    manifest=json.loads((src/"six-venue-handoff.json").read_text())
    if (manifest.get("status")!="SIX_VENUE_SIGNED_HANDOFF_UNEXECUTED" or
            manifest.get("venues")!=list(VENUES) or
            manifest.get("selection_is_gross_only") is not True or
            manifest.get("cost_conversion_verified") is not False or
            any(manifest.get(k) is not False for k in SAFE)):
        raise ValueError("untrusted six-venue signed handoff")
    digests=manifest.get("source_fixtures")
    indices=manifest.get("selected_source_route_indices")
    if (not isinstance(digests,dict) or len(digests)>12 or
            not isinstance(indices,list) or len(indices)>12 or
            len(indices)!=len(set(indices)) or
            any(type(i)is not int or i<0 for i in indices) or
            type(manifest.get("observed_unix"))is not int):
        raise ValueError("invalid signed source selection")
    listing=json.loads((src/"summary.json").read_text())
    selected_rows=[r for r in listing["routes"] if r.get("index") in indices]
    if len(selected_rows)!=len(indices):
        raise ValueError("selected signed routes missing from source manifest")
    for row in selected_rows:
        if row.get("status")!="AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE":
            raise ValueError("unverified source route selected for signing")
    for name,digest in digests.items():
        if (not isinstance(name,str) or not name.endswith(".json") or
                (src/name).resolve().parent!=src.resolve() or
                not isinstance(digest,str) or len(digest)!=64 or
                hashlib.sha256((src/name).read_bytes()).hexdigest()!=digest):
            raise ValueError("signed source fixture digest/path mismatch")
    from arb.m5_distinct_venue_coverage_batch import offline_batch
    signed=offline_batch(rpc,src,dst,observed_unix=manifest["observed_unix"],
                         route_indices=indices)
    return {"status":"SIX_VENUE_SIGNED_OFFLINE_RESEARCH",
            "selected_positive_gross_routes":len(indices),
            "signed_attempted":signed["attempted"],
            "independent_signed_accepted":signed["independent_signed_accepted"],
            "signed_quote_exact_matches":signed.get(
                "observed_venue_quote_exact_matches",0),
            "net_profitable_confirmed":0,
            "reason":"signed fork success does not establish net live profitability",
            "signed_artifact":signed,**SAFE}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase",choices=("source","offline"),required=True)
    parser.add_argument("--rpc",default="http://127.0.0.1:8899")
    parser.add_argument("--registry",default="arb/pool_registry.json")
    parser.add_argument("--discovery-pairs",
                        help="Optional JSON list of up to five explicit mint pairs")
    parser.add_argument("--source-dir",required=True)
    parser.add_argument("--signed-dir")
    parser.add_argument("--amount-in",type=int)
    parser.add_argument("--observed-unix",type=int)
    parser.add_argument("--maximum",type=int,default=12)
    parser.add_argument("--max-cycles",type=int,default=200)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    if args.phase=="source":
        report=source_research(args.rpc,
           json.loads(Path(args.registry).read_text()),args.source_dir,
           amount_in=args.amount_in,observed_unix=args.observed_unix,
           maximum=args.maximum,max_cycles=args.max_cycles,
           discovery_pairs=(json.loads(Path(args.discovery_pairs).read_text())
                            if args.discovery_pairs else None))
    else:
        if not args.signed_dir:
            parser.error("--signed-dir required for offline phase")
        report=offline_research(args.rpc,args.source_dir,args.signed_dir)
    Path(args.output).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"status":report["status"],
                      "actionable":False,"broadcast":False}))


if __name__=="__main__":
    main()
