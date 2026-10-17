"""On-chain AMM account discovery through Surfpool JSON-RPC only.

No Raydium, Orca, or other DEX HTTP APIs. getProgramAccounts scans program
owned accounts; without venue-specific layouts these are CANDIDATES, not pools.
"""
import argparse
import json
import os
from arb.rpc import call
from arb.fork_probe import PROGRAMS

def discover(rpc, programs=None, max_accounts=500):
    programs = programs or PROGRAMS
    if max_accounts < 1:
        raise ValueError("max_accounts must be positive")
    report = {"discovery_type": "program-owned-account-candidates",
              "note": "Not decoded or confirmed liquidity pools", "programs": {}}
    for venue, program_id in programs.items():
        response = call(rpc, "getProgramAccounts", [program_id, {
            "encoding": "base64", "dataSlice": {"offset": 0, "length": 0},
            "commitment": "confirmed"
        }], timeout=90)
        if not isinstance(response, list):
            raise ValueError("unexpected getProgramAccounts response")
        if len(response) > max_accounts:
            raise ValueError(f"{venue}: {len(response)} accounts exceeds limit {max_accounts}; configure narrow layout filters")
        candidates = []
        for item in response:
            value = item.get("account") or {}
            pubkey = item.get("pubkey")
            if not pubkey or value.get("owner") != program_id or value.get("executable") is not False:
                raise ValueError(f"{venue}: invalid program account entry")
            candidates.append(pubkey)
        report["programs"][venue] = {"programId": program_id,
                                     "candidateCount": len(candidates),
                                     "sampleAddresses": candidates[:10]}
    return report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpc", default=os.environ.get("SOLANA_RPC_URL", "http://127.0.0.1:8899"))
    parser.add_argument("--max-accounts", type=int, default=500)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = discover(args.rpc, max_accounts=args.max_accounts)
    text = json.dumps(result, indent=2)
    print(text)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")

if __name__ == "__main__":
    main()
