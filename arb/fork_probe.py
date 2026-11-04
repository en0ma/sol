"""Verify forked mainnet program account presence and optional real pool addresses.

Requires a running Surfpool network fork. Reads only, does not trade.
"""
import json
import os
import sys
from arb.rpc import inspect_account

UPGRADEABLE_LOADER = "BPFLoaderUpgradeab1e11111111111111111111111"

PROGRAMS = {
    "Meteora DLMM": "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo",
    "Orca Whirlpools": "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
    "Raydium CLMM": "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK",
    "Raydium CPMM": "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C",
    "Meteora DAMM v2": "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG",
}

def main():
    url = os.environ.get("SOLANA_RPC_URL", "http://127.0.0.1:8899")
    pools_path = os.environ.get("POOL_MANIFEST", "arb/pools.json")
    with open(pools_path, encoding="utf-8") as file:
        pools = json.load(file)["pools"]
    summary = {"rpc": url, "programs": {}, "pools": []}
    failures = []
    for name, address in PROGRAMS.items():
        acc = inspect_account(url, address)
        summary["programs"][name] = acc
        if not acc["exists"] or not acc["executable"] or acc["owner"] != UPGRADEABLE_LOADER:
            failures.append("program missing, non-executable, or unexpected loader: " + name)
    for pool in pools:
        if pool["venue"] not in PROGRAMS:
            failures.append("unknown pool venue: " + pool["venue"])
            continue
        acc = inspect_account(url, pool["address"], PROGRAMS[pool["venue"]])
        summary["pools"].append({"name": pool["name"], **acc})
        if not acc["exists"] or not acc["owner_matches"] or acc["executable"]:
            failures.append("pool missing, executable, or wrong owner: " + pool["name"])
    summary["failures"] = failures
    print(json.dumps(summary, indent=2))
    return 1 if failures else 0

if __name__ == "__main__":
    sys.exit(main())
