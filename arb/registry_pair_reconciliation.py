"""Source-authenticated registry reconciliation and shared-pair coverage.

Address-only candidates are never promoted to the graph. Symbols are display
metadata, never graph keys; Solana mint addresses are the identity keys.
All admission occurs after owner/vault verification by the existing refresh()
or discovery.verify() engines. No broadcast.
"""
import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

from arb.orca_whirlpool import SOL, USDC
from arb.onchain_pool_discovery import USDT, JUP, RAY
from arb.pool_registry import refresh

SYMBOLS = {SOL: "SOL", USDC: "USDC", USDT: "USDT",
           JUP: "JUP", RAY: "RAY"}
TARGET_PER_VENUE = 20
SAFETY = {"actionable": False, "live_execution_approved": False,
          "broadcast": False}


def reconcile(original, verified, *, target=TARGET_PER_VENUE):
    if (not isinstance(original, list) or not isinstance(verified, list)
            or type(target) is not int or not 1 <= target <= 100):
        raise ValueError("invalid bounded registry reconciliation")
    from arb.onchain_pool_discovery import VENUES
    expected = {}
    for row in original:
        if not isinstance(row, dict) or row.get("venue") not in VENUES:
            raise ValueError("unrecognized registry identity")
        key = (row.get("venue"), row.get("address"))
        if not isinstance(key[1], str) or key in expected:
            raise ValueError("invalid or duplicated registry identity")
        expected[key] = row
    admitted = {}
    for row in verified:
        if not isinstance(row, dict):
            raise ValueError("malformed chain evidence")
        key = (row.get("venue"), row.get("address"))
        if key not in expected or key in admitted:
            raise ValueError("unbound or duplicate onchain identity")
        mint = row.get("mints")
        if (row.get("verified") is not True or
                not isinstance(mint, list) or len(mint) != 2 or
                any(not isinstance(x, str) or len(x) < 32 for x in mint) or
                mint[0] == mint[1] or
                type(row.get("slot")) is not int or row["slot"] < 0):
            raise ValueError("unverified source mint identity")
        prev = expected[key].get("mints")
        if prev is not None and (not isinstance(prev, list) or
                                 sorted(prev) != sorted(mint)):
            raise ValueError("source mint differs from registry")
        amounts = row.get("vault_base_units")
        if (not isinstance(amounts, list) or len(amounts) != 2
                or any(type(v) is not int or v <= 0 for v in amounts)):
            raise ValueError("positive authenticated vault liquidity required")
        admitted[key] = {
            "venue": key[0], "address": key[1], "mints": list(mint),
            "pair": "/".join(SYMBOLS.get(x, x[:8] + "…") for x in mint),
            "symbol_source": "CURATED_DISPLAY_ONLY",
            "slot": row["slot"], "vault_base_units": list(amounts),
            "all_pools_onchain_verified": True,
            "verified": True, **SAFETY}
    pair_venues = defaultdict(set)
    pair_pools = defaultdict(list)
    mint_venues = defaultdict(set)
    for row in admitted.values():
        pair = tuple(sorted(row["mints"]))
        pair_venues[pair].add(row["venue"])
        pair_pools[pair].append({"venue": row["venue"], "address": row["address"]})
        for mint in row["mints"]:
            mint_venues[mint].add(row["venue"])
    shared = []
    for pair, venues in sorted(pair_venues.items()):
        if len(venues) > 1:
            shared.append({"mints": list(pair),
                           "pair": "/".join(SYMBOLS.get(x, x[:8] + "…") for x in pair),
                           "venues": sorted(venues),
                           "pools": sorted(pair_pools[pair],
                                           key=lambda x: (x["venue"], x["address"]))})
    # A pair can have shared mint endpoints yet still fail to close a
    # multi-venue arbitrage route. Run the existing bounded 2–6-leg graph
    # engine on these actual source-authenticated pool identities.
    from arb.registry_multihop_cycles import discover_cycles
    from arb.onchain_pool_discovery import USDT
    graph = discover_cycles(list(admitted.values()),min_hops=2,max_hops=6,
                            starts=(SOL,USDC,USDT),max_cycles=5000)
    cross_venue_cycles=[route for route in graph["cycles"]
                        if len(route["venues"])>=2]
    cycle_pools={(leg["venue"],leg["pool"])
                 for route in cross_venue_cycles for leg in route["legs"]}
    coverage = {}
    # The active pool verifier currently has six venue decoders. The seventh
    # AMM v4 must remain visibly unmet rather than disappearing from the goal.
    for venue in VENUES:
        entries = [row for row in admitted.values() if row["venue"] == venue]
        linked = [row for row in entries if len(pair_venues[tuple(sorted(row["mints"]))]) > 1]
        # An edge touching shared WSOL alone is not necessarily routeable:
        # the OTHER token must also connect beyond this venue to close cycles.
        connected = [row for row in entries if all(len(mint_venues[m]) > 1 for m in row["mints"])]
        routeable=[row for row in entries if (row["venue"],row["address"]) in cycle_pools]
        coverage[venue] = {
            "registered_hints": sum(k[0] == venue for k in expected),
            "authenticated": len(entries),
            "cross_venue_shared_pair": len(linked),
            "cross_venue_mint_connected": len(connected),
            "closed_cross_venue_cycle_pools": len(routeable),
            "target": target,
            "missing_to_target": max(0, target-len(routeable)),
            "target_met": len(routeable) >= target,
        }
    return {
        "status": "SOURCE_AUTHENTICATED_REGISTRY_COVERAGE",
        "source_entries": len(expected), "admitted": len(admitted),
        "unverified_or_missing": len(expected)-len(admitted),
        "pool_target_per_venue": target,
        "seven_venue_target_met": all(v["target_met"] for v in coverage.values()),
        "venue_coverage": coverage, "cross_venue_shared_pairs": shared,
        "authenticated_graph_cycle_count": graph["cycle_count"],
        "cross_venue_closed_cycle_count": len(cross_venue_cycles),
        "graph_inventory_truncated": graph["truncated"],
        "cross_venue_cycle_examples": cross_venue_cycles[:20],
        "graph_pools": list(admitted.values()),
        **SAFETY}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default="arb/pool_registry.json")
    parser.add_argument("--output", required=True)
    parser.add_argument("--rpc", default=os.getenv("SOLANA_RPC_URL", "http://127.0.0.1:8899"))
    parser.add_argument("--min-per-venue", type=int, default=20)
    parser.add_argument("--clean-registry", default="",
                        help="Write only independently verified, mint-complete pool identities")
    args = parser.parse_args()
    # Explicit actual RPC authentication, never copy hint-only mint labels
    # into a supposedly trusted graph.
    from arb.six_venue_pipeline import local_rpc_only
    local_rpc_only(args.rpc)
    original = json.loads(Path(args.registry).read_text())["pools"]
    chain = refresh(args.rpc, original)
    result = reconcile(original, chain["verified_pools"], target=args.min_per_venue)
    result["source_rejections"] = chain["rejected"]
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    if args.clean_registry:
        clean = {"note": "Source-authenticated pool identities; revalidate before every use",
                 "pools": [{"venue": row["venue"], "address": row["address"],
                            "mints": row["mints"], "pair": row["pair"]}
                           for row in result["graph_pools"]]}
        Path(args.clean_registry).write_text(json.dumps(clean, indent=2) + "\n")
    print(json.dumps({k:v for k,v in result.items() if k not in
                      ("graph_pools", "cross_venue_shared_pairs", "source_rejections")}, indent=2))
    return 0 if result["seven_venue_target_met"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
