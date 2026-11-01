"""Read-only seven-venue fork pool-to-route discovery entry point.

Calls the existing authoritative local-Surfpool pool authenticator; does not
invent prices, confirm profit, hydrate, sign, or submit transactions. This is
the first phase of M5 end-to-end delivery; source venue quote adapters and
signed acceptance must run before labeling a route a research opportunity.
"""
import argparse
import json
from pathlib import Path
from arb.next_ten_fork_pool_probe import probe, PROGRAMS
from arb.next_ten_atomic_routes import route_batch
from arb.opportunity_graph import cycles
from arb.pumpswap_local_simulation import local_rpc_only

SAFE = {"actionable": False, "broadcast": False,
        "live_execution_approved": False}
ORDER = tuple(PROGRAMS)


def analyze(readiness, *, max_cycles=200):
    if not isinstance(readiness, dict) or readiness.get("source") != "READ_ONLY_MAINNET_BACKED_SURFPOOL":
        raise ValueError("local source-authentication result required")
    if any(readiness.get(k) is not False for k in SAFE):
        raise ValueError("unsafe source readiness report")
    source = readiness.get("authenticated_pools")
    if not isinstance(source, dict) or set(source) != set(ORDER):
        raise ValueError("seven venue source coverage report required")
    pools = []
    for venue in ORDER:
        if not isinstance(source[venue], list):
            raise ValueError("malformed venue inventory")
        for item in source[venue]:
            if (not isinstance(item, dict) or item.get("venue") != venue
                    or item.get("authenticated") is not True
                    or type(item.get("slot")) is not int or item["slot"] < 0
                    or not isinstance(item.get("pool"), str) or not item["pool"]
                    or any(item.get(k) is not False for k in SAFE)):
                raise ValueError("untrusted source pool record")
            mints = item.get("mints")
            if not isinstance(mints, list) or len(mints) != 2 or any(
                not isinstance(m, str) or not m for m in mints
            ) or mints[0] == mints[1]:
                raise ValueError("invalid source token pair")
            pools.append({"venue": venue, "address": item["pool"],
                          "mints": mints, "verified": True, "slot": item["slot"]})
    # Reserve search capacity for all requested lengths. A naive first-200
    # traversal can contain only two/three hops on dense seven-venue pools.
    # The extra sentinel detects non-exhaustive length-specific searches.
    per_length=max_cycles//5
    budgets={h:per_length+(1 if h-2<max_cycles%5 else 0)
             for h in range(2,7)}
    found=[]
    coverage={}
    truncated=False
    for hops,budget in budgets.items():
        if budget==0:
            coverage[str(hops)]={"returned":0,"budget":0,"truncated":True}
            truncated=True
            continue
        sample=cycles(pools,max_hops=hops,min_hops=hops,
                      max_cycles=budget+1,truncate=True) if pools else []
        length_truncated=len(sample)>budget
        found.extend(sample[:budget])
        coverage[str(hops)]={"returned":min(len(sample),budget),
                             "budget":budget,"truncated":length_truncated}
        truncated=truncated or length_truncated
    routes=found
    from arb.m5_graph_topology_diagnostic import audit
    topology=audit(readiness)
    rows = [{"start_mint": r["start_mint"], "hops": r["hops"],
             "legs": r["legs"], "venue_count": len(r["venues"]),
             "quote_status": "NOT_QUOTED",
             "signed_simulation_status": "NOT_ATTEMPTED",
             "reason": "source-bound venue quotes and common-mint costs not supplied",
             **SAFE} for r in routes]
    return {"status": "SOURCE_AUTHENTICATED_ROUTE_DISCOVERY_ONLY",
            "phase": "DISCOVERY_TO_GRAPH",
            "venue_coverage": {venue: len(source[venue]) for venue in ORDER},
            "authenticated_pool_count": len(pools),
            "connected_cycles": len(rows),
            "cycle_inventory_truncated": truncated,
            "cycle_coverage_by_hops": coverage,
            "authenticated_token_graph_topology": topology,
            "cycle_budget": max_cycles,
            "cycle_count_is_exhaustive": not truncated,
            "distinct_venue_cycles": sum(x["venue_count"] > 1 for x in rows),
            "quoted_candidates": 0, "ranked_profitable_candidates": 0,
            "signed_simulation_attempts": 0,
            "source_pool_check_failures": readiness.get("failed_pool_checks", []),
            "routes": rows, **SAFE}


def scan_local_fork(rpc, registry, *, max_cycles=200):
    local_rpc_only(rpc)
    # Existing seven-venue source checker; no new DEX-specific code.
    pairs = tuple((a, b) for a in ORDER for b in ORDER if a != b)
    readiness = probe(rpc, registry, batch=pairs)
    return analyze(readiness, max_cycles=max_cycles)



def run_m5_research(rpc, registry, *, max_cycles=200, source_dir=None,
                    signed_dir=None, observed_unix=None, maximum=4,
                    quote_input=None,four_to_six_source_output=None):
    """One explicitly offline, existing-engine source -> signed evidence path.

    Signed triangles are independent source-backed candidate probes, NOT
    ranked opportunities from the unquoted graph. Never conflate the two.
    """
    import os
    local_rpc_only(rpc)
    if (signed_dir is not None and (source_dir is None
            or type(observed_unix) is not int or observed_unix < 0)):
        raise ValueError("signed validation requires fixtures and observation time")
    if quote_input is not None and (type(quote_input) is not int
            or not 0<quote_input<2**64 or source_dir is None
            or type(observed_unix) is not int or observed_unix<0):
        raise ValueError("source quote ranking requires fixtures, amount and time")
    if type(maximum) is not int or not 1 <= maximum <= 12:
        raise ValueError("bounded three-venue trial count required")
    if four_to_six_source_output is not None and source_dir is None:
        raise ValueError("four-to-six source output requires explicit fixture mode")
    if (source_dir is not None or signed_dir is not None) and (
            os.environ.get("SURFPOOL_EXPLICITLY_OFFLINE") != "1"):
        raise ValueError("explicit isolated fork gate required for fixture operations")
    pairs = tuple((a, b) for a in ORDER for b in ORDER if a != b)
    readiness = probe(rpc, registry, batch=pairs)
    report = analyze(readiness, max_cycles=max_cycles)
    report["signed_triangle_source_attempts"] = 0
    report["signed_triangle_source_exported"] = 0
    report["independently_signed_triangles_accepted"] = 0
    report["protocol_exact_quote_samples"] = 0
    report["source_triangles"] = {"status": "NOT_REQUESTED"}
    report["source_quote_ranking"] = {"status": "NOT_REQUESTED"}
    report["signed_triangles"] = {"status": "NOT_REQUESTED"}
    report["signed_selection"] = {"status": "NOT_REQUESTED", **SAFE}
    report["four_to_six_source_fixture"] = {"status": "NOT_REQUESTED", **SAFE}
    report["four_to_six_native_quote_chain"] = {"status": "NOT_REQUESTED", **SAFE}
    report["four_to_six_signed_handoff"] = {"status": "NOT_REQUESTED", **SAFE}
    if source_dir is not None:
        from arb.m5_distinct_venue_coverage_batch import source_batch
        exported = source_batch(rpc, readiness, source_dir, maximum=maximum)
        report["source_triangles"] = exported
        report["signed_triangle_source_attempts"] = exported["attempted"]
        report["signed_triangle_source_exported"] = exported["exported"]
        if quote_input is not None:
            from arb.m5_source_triangle_quote_ranking import rank
            root = Path(source_dir)
            fixtures = []
            mapping = []
            for row in exported["routes"]:
                if row["status"] != "AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE":
                    continue
                fixtures.append(json.loads((root / row["fixture"]).read_text()))
                mapping.append(row["index"])
            ranking = rank(fixtures,amount_in=quote_input,
                           observed_unix=observed_unix,maximum=maximum)
            for line in ranking["all_results"]:
                line["source_batch_route_index"] = mapping[line["index"]]
            for line in ranking["ranked"]:
                line["source_batch_route_index"] = mapping[line["index"]]
            report["source_quote_ranking"] = ranking
            report["quoted_candidates"] = ranking["fully_quoted"]
            report["gross_positive_source_quote_routes"] = ranking["positive_gross"]
    if four_to_six_source_output is not None:
        from arb.m5_four_to_six_source_capture import capture
        path=Path(four_to_six_source_output)
        targets=[i for i,r in enumerate(report["routes"]) if 4<=r["hops"]<=6]
        if not targets:
            report["four_to_six_source_fixture"]={
                "status":"NO_AUTHENTICATED_FOUR_TO_SIX_CYCLE_IN_BOUNDED_GRAPH",**SAFE}
        else:
            capture_failures=[]
            chosen_index=None
            result=None
            for index in targets[:8]:
                try:
                    path.parent.mkdir(parents=True,exist_ok=True)
                    result=capture(rpc,report,index,path)
                    chosen_index=index
                    break
                except (ValueError,TypeError,KeyError,RuntimeError) as exc:
                    capture_failures.append({"graph_route_index":index,
                        "reason":str(exc)[:240]})
            if chosen_index is None:
                report["four_to_six_source_fixture"]={
                    "status":"FOUR_TO_SIX_SOURCE_CAPTURE_BLOCKED",
                    "candidate_capture_attempts":len(capture_failures),
                    "candidate_failures":capture_failures,**SAFE}
            else:
              try:
                from arb.m5_four_to_six_signed_handoff import assess
                source=json.loads(path.read_text())
                # Reuse the existing source-native seven-venue dispatcher for
                # this exact graph-selected, manifest-verified 4..6-hop route.
                # Failure of any native leg remains a bounded blocker: never
                # route a fabricated last price to the signer.
                quote_report=None
                if quote_input is not None:
                    from arb.m5_source_indicative_route_chain import research_chain
                    quote_report=research_chain(source,amount_in=quote_input,
                                                observed_unix=observed_unix)
                    report["four_to_six_native_quote_chain"]=quote_report
                    (path.parent/(path.stem+"-native-chain.json")).write_text(
                        json.dumps(quote_report,sort_keys=True,indent=2)+"\n")
                handoff=assess(source,quote_report=quote_report)
                report["four_to_six_signed_handoff"]=handoff
                report["four_to_six_source_fixture"]={
                    **result,"graph_route_index":chosen_index,
                    "candidate_capture_attempts":len(capture_failures)+1,
                    "previous_candidate_failures":capture_failures,
                    "source_fixture_path":str(path),
                    "signed_simulation_verified":False,**SAFE}
              except (ValueError,TypeError,KeyError,RuntimeError) as exc:
                report["four_to_six_native_quote_chain"]={
                    "status":"NATIVE_QUOTE_CHAIN_BLOCKED",
                    "reason":str(exc)[:240],**SAFE}
                report["four_to_six_source_fixture"]={
                    **result,"graph_route_index":chosen_index,
                    "status":"AUTHENTICATED_SOURCE_QUOTE_OR_HANDOFF_BLOCKED",
                    "reason":str(exc)[:240],**SAFE}
    if signed_dir is not None:
        from arb.m5_distinct_venue_coverage_batch import offline_batch
        if quote_input is not None:
            # The very same source fixture index must drive the actual signed
            # attempt. Reject quote-unavailable or non-positive gross cycles;
            # no fee-converted net profitability is inferred here.
            ranking = report["source_quote_ranking"]
            selected = [row["source_batch_route_index"] for row in ranking["ranked"]
                        if row["positive_gross"] is True]
            report["signed_selection"] = {
                "status": "POSITIVE_GROSS_INDICATIVE_ONLY",
                "selected_source_route_indices": selected,
                "unselected_source_routes": report["signed_triangle_source_exported"]-len(selected),
                "net_profitability_verified": False, **SAFE}
            signed = offline_batch(rpc, source_dir, signed_dir,
                                   observed_unix=observed_unix,route_indices=selected)
        else:
            report["signed_selection"] = {
                "status": "SOURCE_COVERAGE_NOT_RANKED",
                "net_profitability_verified": False, **SAFE}
            signed = offline_batch(rpc, source_dir, signed_dir,
                                   observed_unix=observed_unix)
        report["signed_triangles"] = signed
        report["signed_simulation_attempts"] = signed["attempted"]
        report["independently_signed_triangles_accepted"] = signed["independent_signed_accepted"]
        report["protocol_exact_quote_samples"] = signed["independently_validated_quote_samples"]
        # The source-route-index identifies the same fixture from graph-era
        # source export through independently accepted signed simulation.
        # This is signed source-coverage research, not proof that a graph-
        # selected cycle was profitable or that an unpaid fee was settled.
        outcomes=[{"source_route_index":item["index"],
                   "outcome":item.get("simulated_economic_outcome","UNASSESSABLE"),
                   "simulated_estimated_net_start_mint_base_units":
                       item.get("simulated_estimated_net_start_mint_base_units"),
                   "independent_signed_accepted":
                       item.get("independent_signed_accepted") is True,
                   "economics_status":item.get("economics_status"),**SAFE}
                  for item in signed.get("routes",[])]
        report["signed_route_economic_outcomes"]=outcomes
        report["signed_route_economic_outcome_counts"]={
            status:sum(row["outcome"]==status for row in outcomes)
            for status in sorted({row["outcome"] for row in outcomes})}
        report["signed_route_simulated_net_gain_count"]=sum(
            row["outcome"]=="SIMULATED_ESTIMATED_NET_GAIN" for row in outcomes)
        report["realized_net_profit_verified"]=False
        # Join *actual* signed source triangles back to the matching directed
        # graph routes by every pool, mint and venue. Topology-only routes
        # that were not selected stay explicitly unassessed. Never copy one
        # signed triangle's economics onto a different rotation or route.
        signed_by_index={row["source_route_index"]:row for row in outcomes}
        route_keys={}
        for graph_idx,graph_route in enumerate(report["routes"]):
            key=tuple((leg["venue"],leg["pool"],leg["input"],
                       leg["output"]) for leg in graph_route["legs"])
            route_keys.setdefault(key,[]).append(graph_idx)
        matched=set()
        for source_row in report["source_triangles"].get("routes",[]):
            idx=source_row.get("index")
            if (idx not in signed_by_index or
                source_row.get("status")!="AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE"):
                continue
            fixture=json.loads((Path(source_dir)/source_row["fixture"]).read_text())
            venues=fixture.get("route_venues")
            pools=fixture.get("route_pool_addresses")
            mints=fixture.get("route_mints")
            if (not isinstance(venues,list) or len(venues)!=3
                or not isinstance(pools,list) or len(pools)!=3
                or not isinstance(mints,list) or len(mints)!=4):
                raise ValueError("signed graph join requires complete source route identities")
            key=tuple((venues[i],pools[i],mints[i],mints[i+1])
                      for i in range(3))
            for graph_idx in route_keys.get(key,[]):
                report["routes"][graph_idx]["signed_simulation_status"]=(
                    "SOURCE_ROUTE_INDEPENDENTLY_SIGNED" if
                    signed_by_index[idx]["independent_signed_accepted"]
                    else "SOURCE_ROUTE_SIGNED_UNVERIFIED")
                report["routes"][graph_idx]["source_batch_route_index"]=idx
                report["routes"][graph_idx]["simulated_economic_outcome"]=signed_by_index[idx]["outcome"]
                matched.add(graph_idx)
        report["graph_routes_with_source_bound_signed_outcome"]=len(matched)
        report["graph_routes_unassessed_by_signed_batch"]=len(report["routes"])-len(matched)


    return report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpc", default="http://127.0.0.1:8899")
    parser.add_argument("--registry", default="arb/pool_registry.json")
    parser.add_argument("--max-cycles", type=int, default=200)
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-dir")
    parser.add_argument("--signed-dir")
    parser.add_argument("--observed-unix", type=int)
    parser.add_argument("--maximum", type=int, default=4)
    parser.add_argument("--quote-input", type=int)
    parser.add_argument("--four-to-six-source-output")
    args = parser.parse_args()
    if not 1 <= args.max_cycles <= 2000:
        parser.error("bounded maximum cycles must be 1..2000")
    registry = json.loads(Path(args.registry).read_text())
    report = run_m5_research(args.rpc, registry, max_cycles=args.max_cycles,
        source_dir=args.source_dir, signed_dir=args.signed_dir,
        observed_unix=args.observed_unix, maximum=args.maximum,
        quote_input=args.quote_input,
        four_to_six_source_output=args.four_to_six_source_output)
    Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: report[key] for key in (
        "status", "venue_coverage", "authenticated_pool_count", "connected_cycles",
        "distinct_venue_cycles", "quoted_candidates", "signed_simulation_attempts",
        "broadcast")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
