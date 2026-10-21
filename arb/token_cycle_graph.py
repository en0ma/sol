"""Read-only graph enumeration of candidate atomic arbitrage cycles.

Registry mint pairs are UNVERIFIED hints. This module does not quote swaps,
authorize an executable route, or broadcast. Pool adapters must independently
verify accounts and simulate every hop before calling a cycle actionable.
"""
import json
import os
from urllib.request import Request, urlopen
from solders.pubkey import Pubkey
from collections import defaultdict
from pathlib import Path

MAX_POOLS = 500
MIN_INDEX_LIQUIDITY_USD = 50000
MAX_CYCLES = 200
SOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

def fetch_anchor_pool_hints(*, anchors=(SOL, USDC)):
    """Bounded untrusted SOL/* and USDC/* edges; not verified liquidity."""
    pools, errors, seen = [], [], set()
    venues = {"orca": "orca", "raydium": "raydium_unclassified",
              "meteora": "meteora_unclassified", "meteora-dlmm": "meteora_dlmm",
              "pumpswap": "pumpswap"}
    for anchor in anchors:
        try:
            Pubkey.from_string(anchor)
            request = Request(
                "https://api.dexscreener.com/token-pairs/v1/solana/" + anchor,
                headers={"Accept": "application/json", "User-Agent": "sol-fork-research/1"})
            with urlopen(request, timeout=12) as response:
                raw = response.read(524289)
            if len(raw) > 524288:
                raise ValueError("index response over size cap")
            pairs = json.loads(raw)
            if not isinstance(pairs, list):
                raise ValueError("index response must be a list")
            for item in pairs[:200]:
                if not isinstance(item, dict) or item.get("chainId") != "solana":
                    continue
                base, quote = item.get("baseToken"), item.get("quoteToken")
                if not isinstance(base, dict) or not isinstance(quote, dict):
                    continue
                mints = [base.get("address"), quote.get("address")]
                if anchor not in mints or len(set(mints)) != 2:
                    continue
                liquidity = item.get("liquidity")
                try:
                    usd_liquidity = float(liquidity["usd"])
                except (ValueError, TypeError, KeyError):
                    continue
                if not MIN_INDEX_LIQUIDITY_USD <= usd_liquidity < float("inf"):
                    continue
                venue = venues.get(str(item.get("dexId", "")).lower())
                address = item.get("pairAddress")
                if not venue or not isinstance(address, str):
                    continue
                try:
                    Pubkey.from_string(address)
                    for mint in mints:
                        Pubkey.from_string(mint)
                except ValueError:
                    continue
                identity = (venue, address)
                if identity in seen:
                    continue
                seen.add(identity)
                if len(pools) >= 300:
                    break
                pools.append({"venue": venue, "address": address,
                              "mints": mints, "index_liquidity_usd": usd_liquidity,
                              "candidate_source": "UNTRUSTED_PUBLIC_INDEX"})
        except (OSError, TimeoutError, ValueError) as exc:
            errors.append({"anchor": anchor, "error": str(exc)[:200]})
    return pools, errors

def candidate_cycles(entries, *, starts=(SOL, USDC), max_cycles=MAX_CYCLES):
    if type(max_cycles) is not int or not 1 <= max_cycles <= MAX_CYCLES:
        raise ValueError("cycle limit must be bounded")
    if len(entries) > MAX_POOLS:
        raise ValueError("pool registry exceeds bounded graph")
    adjacency = defaultdict(list)
    rejected = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            rejected.append({"reason": "invalid registry entry"})
            continue
        address, venue, mints = entry.get("address"), entry.get("venue"), entry.get("mints")
        if not isinstance(address, str) or not isinstance(venue, str) or (
            not isinstance(mints, list) or len(mints) != 2 or
            not all(isinstance(m, str) and m for m in mints) or mints[0] == mints[1]
        ):
            rejected.append({"address": address, "reason": "no valid two-token mint hint"})
            continue
        key = (venue, address)
        if key in seen:
            rejected.append({"address": address, "reason": "duplicate pool"})
            continue
        seen.add(key)
        a, b = mints
        pool = {"venue": venue, "address": address}
        adjacency[a].append((b, pool))
        adjacency[b].append((a, pool))
    for neighbors in adjacency.values():
        neighbors.sort(key=lambda e: (e[0], e[1]["venue"], e[1]["address"]))
    cycles = []
    identities = set()
    first_token_counts = defaultdict(int)
    unique_starts = list(dict.fromkeys(starts))
    for start_index, start in enumerate(unique_starts):
        # Reserve an equal bounded candidate budget per starting asset.
        start_limit = max_cycles * (start_index + 1) // len(unique_starts)
        if start not in adjacency:
            continue
        def walk(token, path_tokens, legs, used):
            if len(cycles) >= start_limit:
                return
            if len(legs) >= 2 and token == start:
                sig = (start, tuple((leg["pool"], leg["from"], leg["to"])
                                    for leg in legs))
                # Limit concentration in one intermediate token, even if it has many pools.
                first = path_tokens[1]
                cap = max(2, max_cycles // 20)
                if sig not in identities and first_token_counts[(start, first)] < cap:
                    identities.add(sig)
                    first_token_counts[(start, first)] += 1
                    cycles.append({
                        "tokens": path_tokens[:],
                        "legs": legs[:],
                        "hops": len(legs),
                        "venues": sorted({leg["venue"] for leg in legs}),
                        "status": "UNVERIFIED_GRAPH_CANDIDATE",
                        "quote_verified": False,
                        "simulation_verified": False,
                        "actionable": False,
                        "live_execution_approved": False,
                        "broadcast": False,
                    })
                return
            if len(legs) >= 3 or (token in path_tokens[:-1]):
                return
            for destination, pool in adjacency[token]:
                if len(cycles) >= start_limit:
                    return
                identity = (pool["venue"], pool["address"])
                if identity in used:
                    continue
                if destination == start and len(legs) < 1:
                    continue
                if destination != start and destination in path_tokens:
                    continue
                leg = {"venue": pool["venue"], "pool": pool["address"],
                       "from": token, "to": destination}
                walk(destination, path_tokens + [destination],
                     legs + [leg], used | {identity})
        walk(start, [start], [], set())
    return {
        "status": "UNVERIFIED_GRAPH_CANDIDATES",
        "source": "REPOSITORY_REGISTRY_MINT_HINTS",
        "pool_hints_with_mints": len(seen),
        "rejected_hints": rejected,
        "cycles_returned": len(cycles),
        "distinct_intermediates_by_anchor": {
            anchor: len({cycle["tokens"][1] for cycle in cycles if cycle["tokens"][0] == anchor})
            for anchor in unique_starts},
        "truncated": len(cycles) == max_cycles,
        "cycles_by_start": {start: sum(c["tokens"][0] == start for c in cycles)
                            for start in unique_starts},
        "cycles": cycles,
        "actionable": False, "live_execution_approved": False, "broadcast": False,
        "note": "No cycle is executable without all-leg onchain verification, quotes, account setup, atomic signed simulation and settled-balance checks."
    }

def main():
    with Path("arb/pool_registry.json").open() as stream:
        entries = json.load(stream)["pools"]
    index_hints, index_errors = ([], [])
    if os.environ.get("TOKEN_GRAPH_INDEX_ENABLED") == "1":
        index_hints, index_errors = fetch_anchor_pool_hints()
    report = candidate_cycles(entries + index_hints)
    report["registry_entries"] = len(entries)
    report["public_index_hints"] = len(index_hints)
    report["index_min_liquidity_usd"] = MIN_INDEX_LIQUIDITY_USD
    report["public_index_errors"] = index_errors
    report["index_coverage"] = "TWO_ANCHOR_BOUNDED_SAMPLE" if index_hints else "NONE"
    if index_hints:
        report["source"] = "REGISTRY_AND_UNTRUSTED_PUBLIC_INDEX"
    print(json.dumps(report, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
