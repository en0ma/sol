"""Bounded, read-only discovery and signed simulation of alternate SOL/USDC venues.

All accounts originate from local fork RPC. No sendTransaction, airdrops or
remote writes in discovery; cross_venue.run uses only local ephemeral simulation.
A result is never live-actionable, including when simulated PnL is positive.
"""
import json
import os
import base64
from arb.rpc import call
from arb.orca_whirlpool import find_pair, fetch_pool, SOL, USDC
from arb.raydium_cpmm import candidates, verify_vaults, decode, PROGRAM as RAYDIUM_PROGRAM
from arb.rpc import RPCError
from arb.cross_venue import run
from arb.cross_venue_sweep import evaluate
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc

MAX_ORCA = 4
MAX_RAYDIUM = 4
MAX_ROUTES = 6
MAX_FALLBACK_ROUTES = 12
FALLBACK_USDC_SIZES = (1000, 10000, 50000)
TEST_USDC_BASE_UNITS = 10000

def pinned_fallback(rpc):
    """Restricted known-address fallback, NOT discovery of additional pools."""
    report = {"status": "PINNED_FALLBACK_INCOMPLETE",
              "scan_coverage": "PINNED_ADDRESSES_ONLY",
              "broadcast": False, "actionable": False,
              "live_execution_approved": False, "routes": [], "rejections": []}
    # Merge existing address manifests with the bounded repository registry.
    # Mint hints do not establish authenticity: fetch_pool/verify_vaults do.
    with open("arb/whirlpool_pools.json") as f:
        primary_orca = [p["address"] for p in json.load(f)["pools"]]
    with open("arb/raydium_cpmm_pools.json") as f:
        primary_ray = [p["address"] for p in json.load(f)["pools"]]
    with open("arb/pool_registry.json") as f:
        entries = json.load(f)["pools"]
    orca_addresses = list(dict.fromkeys(primary_orca + [
        p["address"] for p in entries
        if p.get("venue") == "orca" and
        (p.get("mints") is None or p["mints"] == [SOL, USDC])]))[:MAX_ORCA]
    ray_addresses = list(dict.fromkeys(primary_ray + [
        p["address"] for p in entries
        if p.get("venue") == "raydium_cpmm" and
        (p.get("mints") is None or p["mints"] == [SOL, USDC])]))[:MAX_RAYDIUM]
    valid_orca = []
    for address in orca_addresses:
        try:
            p = fetch_pool(rpc, address)
            if (p["token_mint_a"], p["token_mint_b"]) != (SOL, USDC):
                raise ValueError("unsupported mint ordering")
            valid_orca.append(address)
        except (ValueError, KeyError, TypeError) as e:
            report["rejections"].append({"orca": address, "reason": str(e)})
    valid_ray = []
    for address in ray_addresses:
        try:
            info = call(rpc, "getAccountInfo", [address, {"encoding": "base64"}])["value"]
            if not info or info["owner"] != RAYDIUM_PROGRAM or info.get("executable"):
                raise ValueError("invalid CPMM owner")
            state = decode(base64.b64decode(info["data"][0], validate=True))
            if (state["token_0_mint"], state["token_1_mint"]) != (SOL, USDC):
                raise ValueError("unsupported mint ordering")
            if verify_vaults(rpc, address, state).get("verified") is not True:
                raise ValueError("unverified CPMM vaults")
            valid_ray.append(address)
        except (ValueError, KeyError, TypeError) as e:
            report["rejections"].append({"raydium": address, "reason": str(e)})
    report["orca_addresses_checked"], report["raydium_addresses_checked"] = len(orca_addresses), len(ray_addresses)
    report["orca_verified"], report["raydium_verified"] = len(valid_orca), len(valid_ray)
    for pool in valid_orca:
        for ray in valid_ray:
            for reverse in (False, True):
                for size in FALLBACK_USDC_SIZES:
                    if len(report["routes"]) >= MAX_FALLBACK_ROUTES:
                        break
                    item = {"orca": pool, "raydium": ray,
                            "direction": "raydium_to_orca" if reverse else "orca_to_raydium",
                            "usdc_amount_base_units": size,
                            "broadcast": False, "actionable": False}
                    try:
                        value = run(rpc, pool, ray, 1000000, size, reverse=reverse)
                        item["simulation"] = {k: v for k, v in value.items()
                                              if k != "log_tail"}
                        item["decision"] = evaluate(value)
                    except (ValueError, KeyError, TypeError) as e:
                        item["status"] = "SIMULATION_BLOCKED"
                        item["reason"] = str(e)
                    report["routes"].append(item)
    report["routes_tested"] = len(report["routes"])
    report["simulated_profitable_candidates"] = sum(
        r.get("decision", {}).get("simulated_profitable") is True for r in report["routes"])
    successful = [r for r in report["routes"]
                  if r.get("simulation", {}).get("cross_venue_success") is True
                  and type(r["simulation"].get("net_wsol_change_lamports")) is int]
    best = max(successful, key=lambda r: r["simulation"]["net_wsol_change_lamports"]) if successful else None
    report["best_net_wsol_change_lamports"] = (
        best["simulation"]["net_wsol_change_lamports"] if best else None)
    report["best_route"] = (
        {"orca": best["orca"], "raydium": best["raydium"],
         "direction": best["direction"],
         "usdc_amount_base_units": best["usdc_amount_base_units"]}
        if best else None)
    report["status"] = "PINNED_FALLBACK_COMPLETE"
    return report

def discover_and_simulate(rpc, max_routes=MAX_ROUTES):
    require_loopback_rpc(rpc)
    if type(max_routes) is not int or not 1 <= max_routes <= MAX_ROUTES:
        raise ValueError("unbounded discovery disabled")
    result = {"status": "DISCOVERY_INCOMPLETE", "source": "LOCAL_MAINNET_BACKED_SURFPOOL",
              "broadcast": False, "live_execution_approved": False,
              "actionable": False, "routes": [], "rejections": []}
    # find_pair performs discriminator, owner and exact mint matching.
    orca = find_pair(rpc, SOL, USDC, max_results=20)
    orca = [p for p in orca if
            (p["token_mint_a"], p["token_mint_b"]) == (SOL, USDC)]
    result["orca_discovered"] = len(orca)
    # CPMM search is restricted to both orders of the exact same mints.
    raydium = candidates(rpc, max_candidates=20)
    eligible = []
    for address, state in sorted(raydium.items()):
        if (state["token_0_mint"], state["token_1_mint"]) != (SOL, USDC):
            continue
        try:
            evidence = verify_vaults(rpc, address, state)
            if evidence.get("verified") is True:
                eligible.append(address)
        except (ValueError, KeyError, TypeError) as e:
            result["rejections"].append({"raydium": address, "reason": str(e)})
    result["raydium_verified"] = len(eligible)
    result["orca_considered"] = min(len(orca), MAX_ORCA)
    result["raydium_considered"] = min(len(eligible), MAX_RAYDIUM)
    for pool in orca[:MAX_ORCA]:
        for ray in eligible[:MAX_RAYDIUM]:
            if len(result["routes"]) >= max_routes:
                break
            for reverse in (False, True):
                if len(result["routes"]) >= max_routes:
                    break
                route = {"orca": pool["address"], "raydium": ray,
                         "direction": "raydium_to_orca" if reverse else "orca_to_raydium",
                         "usdc_amount_base_units": TEST_USDC_BASE_UNITS,
                         "actionable": False, "broadcast": False}
                try:
                    simulated = run(rpc, pool["address"], ray, 1000000,
                                    TEST_USDC_BASE_UNITS, reverse=reverse)
                    route["simulation"] = {k: v for k, v in simulated.items()
                                           if k != "log_tail"}
                    route["decision"] = evaluate(simulated)
                except (ValueError, KeyError, TypeError) as e:
                    route["status"] = "SIMULATION_BLOCKED"
                    route["reason"] = str(e)
                result["routes"].append(route)
        if len(result["routes"]) >= max_routes:
            break
    result["status"] = "BOUNDED_DISCOVERY_COMPLETE"
    result["routes_tested"] = len(result["routes"])
    result["simulated_profitable_candidates"] = sum(
        r.get("decision", {}).get("simulated_profitable") is True
        for r in result["routes"])
    return result

def main():
    rpc = os.environ.get("SOLANA_RPC_URL", "http://127.0.0.1:8899")
    try:
        report = discover_and_simulate(rpc)
    except (RPCError, TimeoutError, OSError) as exc:
        # An upstream provider rate limit is NOT evidence that no pools exist.
        message = str(exc)
        report = {"status": "DISCOVERY_BLOCKED_UPSTREAM_RATE_LIMIT"
                  if "429" in message or "Too Many Requests" in message
                  else "DISCOVERY_BLOCKED_RPC",
                  "reason": message[:400], "routes": [],
                  "pool_counts_verified": False, "broadcast": False,
                  "actionable": False, "live_execution_approved": False}
    if report.get("status") == "DISCOVERY_BLOCKED_UPSTREAM_RATE_LIMIT":
        try:
            limited = pinned_fallback(rpc)
            limited["upstream_scan_status"] = report["status"]
            report = limited
        except (RPCError, TimeoutError, OSError, ValueError) as exc:
            report["pinned_fallback_error"] = str(exc)[:400]
    path = os.environ.get("CROSS_VENUE_DISCOVERY_REPORT")
    if path:
        with open(path, "w") as f:
            json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] in ("BOUNDED_DISCOVERY_COMPLETE", "PINNED_FALLBACK_COMPLETE") else 2

if __name__ == "__main__":
    raise SystemExit(main())
