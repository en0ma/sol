"""Read-only Whirlpool validation report with explicit PASS / NOT_CONFIGURED / FAIL.

Never silently interprets an empty manifest as pool validation.
"""
import json
import os
import sys
from arb.verify_whirlpool import verify

def main():
    rpc = os.environ.get("SOLANA_RPC_URL", "http://127.0.0.1:8899")
    path = os.environ.get("WHIRLPOOL_MANIFEST", "arb/whirlpool_pools.json")
    with open(path, encoding="utf-8") as f:
        pools = json.load(f)["pools"]
    if not pools:
        result = {"status": "NOT_CONFIGURED", "verifiedPools": 0,
                  "reason": "No on-chain verified pool addresses pinned; pool swap testing remains blocked"}
        code = 0
    else:
        try:
            states = verify(rpc, pools)
            result = {"status": "PASS", "verifiedPools": len(states), "states": states}
            code = 0
        except (ValueError, KeyError, RuntimeError) as exc:
            result = {"status": "FAIL", "verifiedPools": 0, "error": str(exc)}
            code = 1
    print(json.dumps(result, indent=2))
    output = os.environ.get("POOL_VERIFICATION_REPORT")
    if output:
        with open(output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
    return code

if __name__ == "__main__":
    sys.exit(main())
