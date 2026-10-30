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




def report_signed_source_cycle_preflight(registry, readiness, graph):
    """Bind preflight to the SAME authenticated original source graph.

    This is evidence inventory only: neither historical signed provenance
    nor same-source pool authentication proves executable fresh quotes.
    No additional network reads, separate coordinator, or registry mutation.
    """
    from arb.six_venue_registry_eligibility import screen_signed_provenance
    if (not isinstance(graph,dict) or
        graph.get("status")!="SIX_VENUE_AUTHENTICATED_GRAPH_ONLY" or
        any(graph.get(k) is not False for k in SAFE) or
        not isinstance(readiness,dict) or
        readiness.get("source")!="READ_ONLY_MAINNET_BACKED_SURFPOOL" or
        any(readiness.get(k) is not False for k in SAFE)):
        raise ValueError("same source authenticated graph required")
    # A caller cannot pair a legitimate source inventory with a forged or
    # stale graph. Regenerate the bounded topology from these exact source
    # identities and compare its complete route inventory.
    expected=authenticated_graph(readiness,max_cycles=len(graph.get("routes",[])) or 1)
    if (graph.get("source_pool_count")!=expected["source_pool_count"] or
        graph.get("venue_pool_counts")!=expected["venue_pool_counts"] or
        graph.get("routes")!=expected["routes"] or
        graph.get("cycle_inventory_truncated")!=expected["cycle_inventory_truncated"]):
        raise ValueError("source graph is not bound to authenticated source inventory")
    signed=screen_signed_provenance(registry)
    approved={(p["venue"],p["address"]):p for p in signed["candidates"]}
    rows=[]
    for venue in VENUES:
        for row in readiness.get("authenticated_pools",{}).get(venue,[]):
            key=(venue,row.get("pool"))
            previous=approved.get(key)
            if previous is None:
                continue
            if (row.get("authenticated") is not True or
                row.get("mints")!=previous["mints"] or
                type(row.get("slot")) is not int or row["slot"]<0 or
                any(row.get(k) is not False for k in SAFE)):
                raise ValueError("signed pool and fresh original source identity disagree")
            rows.append({"venue":venue,"address":key[1],"mints":list(previous["mints"]),
                         "source_identity_refreshed":True,
                         "current_source_slot":row["slot"],
                         "current_complete_fee_and_tick_state_verified":False,
                         "current_native_sdk_signed_quote_verified":False,
                         "coordinator_eligible":False})
    fresh={"status":"FRESH_IDENTITY_ONLY_NOT_USABLE_REGISTRY_ADMISSION",
           "source_authenticated":rows,"coordinator_eligible_count":0,**SAFE}
    explicit=[]
    for route in graph["routes"]:
        legs=route["legs"]
        tokens=[legs[0]["input"]]+[leg["output"] for leg in legs]
        explicit.append({"legs":[{"venue":leg["venue"],"pool":leg["pool"],
                                  "input_mint":leg["input"],"output_mint":leg["output"]}
                                 for leg in legs],"tokens":tokens})
    return preflight_candidate_cycles_against_registry(registry,fresh,explicit)



def source_research(rpc, registry, fixture_dir, *, amount_in,
                    observed_unix, maximum=12, max_cycles=200,
                    discovery_pairs=None,pool_probe_limit=4):
    """Read-only source-backed Surfpool: authenticated pools -> ranked fixtures.

    This phase MUST complete and stop before a separate --offline Surfpool
    process executes signed simulations. Never sign against a source fork.
    """
    local_rpc_only(rpc)
    if (type(amount_in)is not int or not 0<amount_in<2**64 or
            type(observed_unix)is not int or observed_unix<0 or
            type(maximum)is not int or not 1<=maximum<=12 or
            not isinstance(registry,dict) or
            type(pool_probe_limit)is not int or not 1<=pool_probe_limit<=12):
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
    # Bound the initial onchain probe to avoid long, rate-limited scanning
    # across large historical registries; select the first N for each venue.
    # More source rows may be processed in subsequent incremental passes.
    budgets={venue:0 for venue in VENUES}
    bounded=[]
    for item in registry.get("pools",[]):
        if not isinstance(item,dict):
            continue
        venue=item.get("venue")
        if venue in budgets and budgets[venue]<pool_probe_limit:
            bounded.append(item)
            budgets[venue]+=1
    scoped_registry={**registry,"pools":bounded}
    batch=tuple((a,b) for a in VENUES for b in VENUES if a!=b)
    readiness=probe(rpc,scoped_registry,batch=batch)
    if set(readiness.get("authenticated_pools",{}))!=set(VENUES):
        raise ValueError("unexpected source venue coverage")
    graph=authenticated_graph(readiness,max_cycles=max_cycles)
    source_cycle_preflight=report_signed_source_cycle_preflight(registry,readiness,graph)
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
    from arb.six_venue_quote_continuity import audit_ranked_source_quote_continuity
    quote_continuity=audit_ranked_source_quote_continuity(ranking,fixtures,amount_in)
    positive=[indices[row["index"]] for row in ranking["ranked"]
              if row.get("positive_gross") is True]
    # A gross-loss route can still provide valuable signed CI diagnostics.
    # Only when there are NO positive-gross candidates, sign one source-
    # quotable route as an explicitly non-opportunity diagnostic sample.
    diagnostic=([indices[ranking["ranked"][0]["index"]]]
                if not positive and ranking["ranked"] else [])
    selected=positive if positive else diagnostic
    selection_mode=("POSITIVE_GROSS_RESEARCH" if positive else
                    "NONPROFITABLE_DIAGNOSTIC_ONLY" if diagnostic else
                    "NO_QUOTABLE_ROUTE")
    summary_raw=(root/"summary.json").read_bytes()
    ranking_raw=json.dumps(ranking,sort_keys=True,separators=(",",":")).encode()
    (root/"six-venue-ranking.json").write_bytes(ranking_raw)
    preflight_raw=json.dumps(source_cycle_preflight,sort_keys=True,separators=(",",":")).encode()
    (root/"six-venue-source-cycle-preflight.json").write_bytes(preflight_raw)
    continuity_raw=json.dumps(quote_continuity,sort_keys=True,separators=(",",":")).encode()
    (root/"six-venue-quote-continuity.json").write_bytes(continuity_raw)
    manifest={"status":"SIX_VENUE_SIGNED_HANDOFF_UNEXECUTED",
              "venues":list(VENUES),"observed_unix":observed_unix,
              "amount_in":amount_in,"source_fixtures":digests,
              "source_summary_sha256":hashlib.sha256(summary_raw).hexdigest(),
              "source_ranking_sha256":hashlib.sha256(ranking_raw).hexdigest(),
              "source_cycle_preflight_sha256":hashlib.sha256(preflight_raw).hexdigest(),
              "source_quote_continuity_sha256":hashlib.sha256(continuity_raw).hexdigest(),
              "selected_source_route_indices":selected,
              "positive_gross_indices":positive,
              "diagnostic_only_indices":diagnostic,
              "selection_mode":selection_mode,
              "selection_is_gross_only":True,
              "cost_conversion_verified":False,**SAFE}
    root.mkdir(parents=True,exist_ok=True)
    (root/"six-venue-handoff.json").write_text(json.dumps(manifest,indent=2)+"\n")
    return {"status":"SIX_VENUE_SOURCE_AND_QUOTE_RESEARCH",
            "discovery":{"venue_owned_search":discovery,
                         "authenticated_pools":graph["source_pool_count"],
                         "failed_pool_checks":len(readiness.get("failed_pool_checks",[])),
                         "registry_pool_probe_limit_per_venue":pool_probe_limit},
            "graph":{"candidate_cycles":graph["candidate_cycles"],
                     "truncated":graph["cycle_inventory_truncated"]},
            "quote":{"source_fixtures_exported":source["exported"],
                     "fully_quoted":ranking["fully_quoted"],
                     "blocked":ranking["blocked"],
                     "gross_positive":ranking["positive_gross"],
                     "net_profitable_confirmed":0},
            "signed_simulation_status":"NOT_ATTEMPTED",
            "manifest":manifest,"graph_artifact":graph,
            "source_cycle_preflight":source_cycle_preflight,
            "source_quote_continuity":quote_continuity,
            "ranking_artifact":ranking,**SAFE}




def preflight_candidate_cycles_against_registry(registry, fresh_report, routes):
    """Bridge existing shared registry and authenticated graph to 2-6 hop screens.

    A route must contain explicit token and pool identity. No route is promoted
    to the coordinator here; current fee/tick pricing and signed full-route
    acceptance are still separate evidence gates. Keep blocked routes visible.
    """
    from arb.six_venue_registry_eligibility import screen_signed_provenance
    from arb.six_venue_cycle_eligibility import screen_cycle_source_eligibility
    provenance=screen_signed_provenance(registry)
    if (not isinstance(routes,list) or len(routes)>MAX_CYCLES or
        not isinstance(fresh_report,dict) or
        fresh_report.get("status") not in (
            "FRESH_IDENTITY_ONLY_NOT_USABLE_REGISTRY_ADMISSION","NO_SCREENED_POOLS") or
        any(fresh_report.get(k) is not False for k in SAFE)):
        raise ValueError("bounded fail-closed route preflight required")
    provenance_keys={(r["venue"],r["address"]) for r in provenance["candidates"]}
    results=[]
    for index,route in enumerate(routes):
        if not isinstance(route,dict):
            raise ValueError("malformed candidate cycle")
        legs=route.get("legs")
        tokens=route.get("tokens")
        if not isinstance(legs,list) or not isinstance(tokens,list):
            results.append({"index":index,"status":"BLOCKED_MISSING_EXPLICIT_ROUTE_MINTS_OR_LEGS",
                            "coordinator_eligible":False,**SAFE})
            continue
        try:
            for leg in legs:
                if not isinstance(leg,dict) or (leg.get("venue"),leg.get("pool")) not in provenance_keys:
                    raise ValueError("route pool lacks signed provenance")
            accepted=screen_cycle_source_eligibility(legs,tokens,fresh_report)
            results.append({"index":index,"status":accepted["status"],
                            "legs":accepted["legs"],"coordinator_eligible":False,**SAFE})
        except (ValueError,TypeError) as exc:
            results.append({"index":index,"status":"BLOCKED_ROUTE_SOURCE_INELIGIBLE",
                            "reason":str(exc)[:180],"coordinator_eligible":False,**SAFE})
    return {"status":"SIX_VENUE_ROUTE_SOURCE_PREFLIGHT_ONLY",
            "routes_screened":len(results),
            "source_identity_routes":sum(r["status"]=="SOURCE_IDENTITY_CYCLE_ONLY_PRICING_NOT_VERIFIED"
                                         for r in results),
            "blocked_routes":sum(r["status"]!="SOURCE_IDENTITY_CYCLE_ONLY_PRICING_NOT_VERIFIED"
                                 for r in results),
            "coordinator_eligible_routes":0,"routes":results,**SAFE}


def assess_signed_batch(batch, selected):
    """Separate authenticated signed outcome from gross-only quote ranking."""
    if (not isinstance(batch,dict) or not isinstance(selected,list) or
            len(selected)!=len(set(selected)) or
            any(type(i)is not int for i in selected)):
        raise ValueError("malformed signed batch selection")
    rows=batch.get("routes")
    if (not isinstance(rows,list) or len(rows)!=len(selected) or
            batch.get("attempted")!=len(selected) or
            any(not isinstance(row,dict) for row in rows) or
            len({row.get("index") for row in rows})!=len(rows) or
            {row["index"] for row in rows}!=set(selected) or
            any(row.get("actionable") is not False or
                row.get("broadcast") is not False for row in rows)):
        raise ValueError("signed route report missing or inconsistent with source selection")
    verified=sum(row.get("independent_signed_accepted") is True for row in rows)
    if (batch.get("independent_signed_accepted")!=verified or
            any(row.get("independent_signed_accepted") not in (True,False)
                for row in rows)):
        raise ValueError("signed independent acceptance count inconsistent")
    decisions=[]
    for row in sorted(rows,key=lambda r:r["index"]):
        accepted=row["independent_signed_accepted"] is True
        gross=row.get("gross_start_mint_delta") if accepted else None
        budget=row.get("break_even_total_cost_budget_start_mint_base_units") if accepted else None
        units=row.get("observed_compute_units") if accepted else None
        # Signed outcome flags alone do not authorize untrusted numeric fields.
        # An accepted receipt's optional economic quantities must be exact
        # integers and the break-even budget must equal positive gross margin.
        if accepted:
            if (gross is not None and type(gross) is not int or
                budget is not None and (type(budget) is not int or budget < 0) or
                units is not None and (type(units) is not int or
                                       not 0 < units <= 1_400_000) or
                budget is not None and (gross is None or budget != max(0,gross))):
                raise ValueError("signed gross, compute or break-even budget inconsistent")
        decisions.append({
            "index":row["index"],
            "stage":("SIGNED_FORK_CPI_ROLLBACK_ACCEPTED" if accepted else
                     "SIGNED_FORK_REJECTED"),
            "signed_execution_verified":accepted,
            "source_price_economics_gate":row.get("source_price_economics_gate"),
            "economics_status":row.get("economics_status"),
            "observed_gross_delta_start_mint_base_units":
                row.get("gross_start_mint_delta") if accepted else None,
            "observed_compute_units":
                row.get("observed_compute_units") if accepted else None,
            "maximum_affordable_total_cost_start_mint_base_units":
                row.get("break_even_total_cost_budget_start_mint_base_units")
                if accepted else None,
            "network_fee_conversion_verified":False,
            "net_profitability_verified":False,**SAFE})
    gross_ranked=sorted(
        (item for item in decisions if
            type(item["observed_gross_delta_start_mint_base_units"]) is int),
        key=lambda item:item["observed_gross_delta_start_mint_base_units"],
        reverse=True)
    return {"status":"SIX_VENUE_SIGNED_ROUTE_DECISIONS",
            "selected":len(selected),"signed_accepted":verified,
            "gross_ranked_signed_research":gross_ranked,
            "signed_rejected":len(selected)-verified,
            "net_profitable_candidates":0,
            "decisions":decisions,**SAFE}



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
    summary_raw=(src/"summary.json").read_bytes()
    ranking_raw=(src/"six-venue-ranking.json").read_bytes()
    preflight_raw=(src/"six-venue-source-cycle-preflight.json").read_bytes()
    if hashlib.sha256(preflight_raw).hexdigest()!=manifest.get("source_cycle_preflight_sha256"):
        raise ValueError("source cycle preflight digest mismatch")
    preflight=json.loads(preflight_raw)
    if (not isinstance(preflight,dict) or
        preflight.get("status")!="SIX_VENUE_ROUTE_SOURCE_PREFLIGHT_ONLY" or
        preflight.get("coordinator_eligible_routes")!=0 or
        any(preflight.get(k) is not False for k in SAFE) or
        type(preflight.get("routes_screened")) is not int or
        not isinstance(preflight.get("routes"),list) or
        len(preflight["routes"])!=preflight["routes_screened"] or
        any(not isinstance(route,dict) or route.get("coordinator_eligible") is not False
            or any(route.get(k) is not False for k in SAFE)
            for route in preflight["routes"])):
        raise ValueError("source cycle preflight not fail-closed")
    if (hashlib.sha256(summary_raw).hexdigest()!=manifest.get("source_summary_sha256") or
            hashlib.sha256(ranking_raw).hexdigest()!=manifest.get("source_ranking_sha256")):
        raise ValueError("signed source inventory or ranking digest mismatch")
    continuity_raw=(src/"six-venue-quote-continuity.json").read_bytes()
    if hashlib.sha256(continuity_raw).hexdigest()!=manifest.get("source_quote_continuity_sha256"):
        raise ValueError("source quote continuity digest mismatch")
    continuity=json.loads(continuity_raw)
    if (not isinstance(continuity,dict) or
        continuity.get("status")!="SOURCE_QUOTE_CONTINUITY_ARITHMETIC_ONLY" or
        continuity.get("current_native_sdk_parity_verified") is not False or
        continuity.get("coordinator_eligible_routes")!=0 or
        any(continuity.get(k) is not False for k in SAFE)):
        raise ValueError("source quote continuity falsely approved pricing")
    listing=json.loads(summary_raw)
    ranking=json.loads(ranking_raw)
    if (ranking.get("status")!="GROSS_SOURCE_BOUND_RANKING_ONLY" or
            any(r.get("actionable") is not False for r in ranking.get("ranked",[]))):
        raise ValueError("signed source ranking status invalid")
    original=[r for r in listing["routes"]
              if r.get("status")=="AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE"]
    try:
        derived=[original[r["index"]]["index"] for r in ranking["ranked"]
                 if r.get("positive_gross") is True]
    except (TypeError,IndexError,KeyError) as exc:
        raise ValueError("signed source quote ranking index invalid") from exc
    diagnostic=([original[ranking["ranked"][0]["index"]]["index"]]
                if not derived and ranking["ranked"] else [])
    expected=derived if derived else diagnostic
    if (expected!=indices or
            manifest.get("positive_gross_indices")!=derived or
            manifest.get("diagnostic_only_indices")!=diagnostic or
            manifest.get("selection_mode")!=(
                "POSITIVE_GROSS_RESEARCH" if derived else
                "NONPROFITABLE_DIAGNOSTIC_ONLY" if diagnostic else
                "NO_QUOTABLE_ROUTE")):
        raise ValueError("signed selection differs from frozen native quote ranking")
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
    from arb.six_venue_quote_continuity import audit_ranked_source_quote_continuity
    frozen_fixtures=[]
    for row in original:
        name=row.get("fixture")
        if (not isinstance(name,str) or name not in digests or
            (src/name).resolve().parent!=src.resolve()):
            raise ValueError("ranked source fixture missing from signed digest manifest")
        frozen_fixtures.append(json.loads((src/name).read_bytes()))
    independently_recomputed=audit_ranked_source_quote_continuity(
        ranking,frozen_fixtures,manifest["amount_in"])
    if independently_recomputed!=continuity:
        raise ValueError("source quote continuity does not match original signed source ranking")
    from arb.m5_distinct_venue_coverage_batch import offline_batch
    signed=offline_batch(rpc,src,dst,observed_unix=manifest["observed_unix"],
                         route_indices=indices)
    decisions=assess_signed_batch(signed,indices)
    return {"status":"SIX_VENUE_SIGNED_OFFLINE_RESEARCH",
            "selected_positive_gross_routes":len(manifest["positive_gross_indices"]),
            "diagnostic_only_signed_routes":len(manifest["diagnostic_only_indices"]),
            "selection_mode":manifest["selection_mode"],
            "route_decisions":decisions,
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
    parser.add_argument("--pool-probe-limit",type=int,default=4)
    parser.add_argument("--max-cycles",type=int,default=200)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    if args.phase=="source":
        report=source_research(args.rpc,
           json.loads(Path(args.registry).read_text()),args.source_dir,
           amount_in=args.amount_in,observed_unix=args.observed_unix,
           maximum=args.maximum,max_cycles=args.max_cycles,
           pool_probe_limit=args.pool_probe_limit,
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
