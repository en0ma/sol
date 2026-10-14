"""Verify an explicit Whirlpool address via local Surfpool RPC.

No DEX APIs and no broad getProgramAccounts scans. The address must be provided
in a checked-in fixture manifest or environment variable.
"""
import argparse
import json
import os
from arb.orca_whirlpool import fetch_pool, SOL, USDC

def verify(rpc, pools):
    if not pools:
        raise ValueError("No verified pool addresses supplied")
    output = []
    for pool in pools:
        address = pool["address"]
        state = fetch_pool(rpc, address)
        expected = set(pool.get("mints", [SOL, USDC]))
        if len(expected) != 2 or {state["token_mint_a"], state["token_mint_b"]} != expected:
            raise ValueError("Unexpected token mints for " + address)
        if int(state["liquidity"]) <= 0:
            raise ValueError("Zero Whirlpool liquidity for " + address)
        output.append(state)
    return output

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rpc", default=os.getenv("SOLANA_RPC_URL","http://127.0.0.1:8899"))
    p.add_argument("--manifest", default="arb/whirlpool_pools.json")
    args = p.parse_args()
    with open(args.manifest,encoding="utf-8") as f:
        pools = json.load(f)["pools"]
    if not pools:
        print("No pinned Whirlpool addresses; live pool verification not executed.")
        return 2
    print(json.dumps(verify(args.rpc,pools),indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
