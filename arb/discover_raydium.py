"""Discover SOL/USDC Raydium pools from official API, then validate on-chain ownership.

Read-only. API metadata is untrusted: addresses must pass RPC ownership checks.
Writes a JSON manifest only when --output is provided.
"""
import argparse
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from arb.rpc import inspect_account

SOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
PROGRAMS = {
    "Raydium CLMM": "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK",
    "Raydium CPMM": "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C",
}

def discover(fetch=None):
    query = urlencode({"mint1": SOL, "mint2": USDC, "poolType": "all",
                       "poolSortField": "liquidity", "sortType": "desc",
                       "pageSize": 30, "page": 1})
    url = "https://api-v3.raydium.io/pools/info/mint?" + query
    if fetch is None:
        def fetch(address):
            with urlopen(Request(address, headers={"Accept": "application/json"}), timeout=20) as r:
                return json.load(r)
    data = fetch(url)
    if data.get("success") is not True:
        raise ValueError("Raydium API did not return success=true")
    items = data.get("data", {}).get("data", [])
    results = []
    for item in items:
        program = item.get("programId")
        venue = next((name for name, owner in PROGRAMS.items() if owner == program), None)
        pool = item.get("id")
        if venue and isinstance(pool, str):
            mints = {item.get("mintA", {}).get("address"), item.get("mintB", {}).get("address")}
            if mints == {SOL, USDC}:
                results.append({"name": "SOL/USDC " + venue, "venue": venue,
                                "address": pool, "programId": program,
                                "tvlUsdReported": item.get("tvl")})
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpc", default="http://127.0.0.1:8899")
    parser.add_argument("--output")
    args = parser.parse_args()
    pools = discover()
    verified = []
    for pool in pools:
        state = inspect_account(args.rpc, pool["address"], pool["programId"])
        if state["exists"] and state["owner_matches"] and not state["executable"]:
            verified.append({**pool, "account": state})
    print(json.dumps({"discovered": len(pools), "verified": len(verified),
                      "pools": verified}, indent=2))
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump({"pools": [{k: p[k] for k in ("name", "venue", "address")}
                                 for p in verified]}, f, indent=2)
    if not verified:
        raise SystemExit("No live Raydium CLMM/CPMM SOL/USDC pools verified")

if __name__ == "__main__":
    main()
