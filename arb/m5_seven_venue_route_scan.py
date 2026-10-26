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
    routes = cycles(pools, max_cycles=max_cycles) if pools else []
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
                    quote_input=None):
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
            report["source_quote_ranking"] = ranking
            report["quoted_candidates"] = ranking["fully_quoted"]
            report["gross_positive_source_quote_routes"] = ranking["positive_gross"]
    if signed_dir is not None:
        from arb.m5_distinct_venue_coverage_batch import offline_batch
        signed = offline_batch(rpc, source_dir, signed_dir,
                               observed_unix=observed_unix)
        report["signed_triangles"] = signed
        report["signed_simulation_attempts"] = signed["attempted"]
        report["independently_signed_triangles_accepted"] = signed["independent_signed_accepted"]
        report["protocol_exact_quote_samples"] = signed["independently_validated_quote_samples"]
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
    args = parser.parse_args()
    if not 1 <= args.max_cycles <= 2000:
        parser.error("bounded maximum cycles must be 1..2000")
    registry = json.loads(Path(args.registry).read_text())
    report = run_m5_research(args.rpc, registry, max_cycles=args.max_cycles,
        source_dir=args.source_dir, signed_dir=args.signed_dir,
        observed_unix=args.observed_unix, maximum=args.maximum,
        quote_input=args.quote_input)
    Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: report[key] for key in (
        "status", "venue_coverage", "authenticated_pool_count", "connected_cycles",
        "distinct_venue_cycles", "quoted_candidates", "signed_simulation_attempts",
        "broadcast")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
