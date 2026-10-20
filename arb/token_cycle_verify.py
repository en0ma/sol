"""Fail-closed on-chain verification for read-only token-cycle candidates.

Verification is NOT a quote, signed simulation or execution approval.
Currently supports Orca Whirlpool and Raydium CPMM. Other venues remain
unverified rather than being silently mapped to an incorrect program.
"""
import base64
import json
import os
from arb.rpc import call, RPCError
from arb.orca_whirlpool import fetch_pool, SOL, USDC
from arb.raydium_cpmm import PROGRAM as RAYDIUM_PROGRAM, decode, verify_vaults
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc

MAX_UNIQUE_POOLS = 60

def verify_graph(rpc, graph):
    require_loopback_rpc(rpc)
    pool_hints = {}
    for cycle in graph.get("cycles", []):
        if cycle.get("tokens", [None])[0] != cycle.get("tokens", [None])[-1]:
            raise ValueError("non-closed cycle was supplied")
        for leg in cycle.get("legs", []):
            key = (leg["venue"], leg["pool"])
            pool_hints.setdefault(key, set()).add(frozenset((leg["from"], leg["to"])))
    # Avoid hiding unsampled candidate pools beyond the bounded verification cap.
    keys = sorted(pool_hints)
    examined = keys[:MAX_UNIQUE_POOLS]
    verification = {}
    for venue, address in examined:
        reason = None
        try:
            if venue == "orca":
                state = fetch_pool(rpc, address)
                mints = frozenset((state["token_mint_a"], state["token_mint_b"]))
            elif venue == "raydium_cpmm":
                info = call(rpc, "getAccountInfo", [address, {"encoding": "base64"}])["value"]
                if not info or info.get("owner") != RAYDIUM_PROGRAM or info.get("executable"):
                    raise ValueError("invalid Raydium CPMM program owner")
                data = info.get("data")
                if not isinstance(data, list) or len(data) != 2 or data[1] != "base64":
                    raise ValueError("bad CPMM base64 response")
                state = decode(base64.b64decode(data[0], validate=True))
                if verify_vaults(rpc, address, state).get("verified") is not True:
                    raise ValueError("CPMM vaults not verified")
                mints = frozenset((state["token_0_mint"], state["token_1_mint"]))
            else:
                reason = "unsupported venue adapter"
            if reason is None and (len(mints) != 2 or mints not in pool_hints[(venue, address)]):
                reason = "on-chain token mints disagree with graph hint"
        except (ValueError, KeyError, TypeError, RPCError, OSError, TimeoutError) as exc:
            reason = str(exc)[:240]
        verification[(venue, address)] = {
            "onchain_verified": reason is None,
            "reason": reason
        }
    cycles = []
    for cycle in graph.get("cycles", []):
        proofs = [verification.get((leg["venue"], leg["pool"])) for leg in cycle["legs"]]
        valid = bool(proofs) and all(p and p["onchain_verified"] for p in proofs)
        cycles.append({
            "tokens": cycle["tokens"], "legs": cycle["legs"],
            "all_pools_onchain_verified": valid,
            "status": "POOL_STATES_VERIFIED_NOT_SIMULATED" if valid else "POOL_VERIFICATION_INCOMPLETE",
            "rejection_reasons": [p["reason"] if p else "outside pool verification cap"
                                  for p in proofs if not p or not p["onchain_verified"]],
            "quote_verified": False, "simulation_verified": False,
            "actionable": False, "live_execution_approved": False, "broadcast": False,
        })
    return {
        "status": "READ_ONLY_GRAPH_VERIFICATION",
        "cycles_checked": len(cycles),
        "cycles_with_all_pools_verified": sum(c["all_pools_onchain_verified"] for c in cycles),
        "unique_pools_examined": len(examined),
        "unique_pools_skipped_cap": len(keys) - len(examined),
        "cycles": cycles,
        "actionable": False, "live_execution_approved": False, "broadcast": False,
        "note": "Verified pools are NOT executable routes without verified quotes, instruction builders and signed atomic simulation."
    }

def main():
    with open(os.environ["TOKEN_GRAPH_CANDIDATES_REPORT"]) as stream:
        graph = json.load(stream)
    rpc = os.environ.get("SOLANA_RPC_URL", "http://127.0.0.1:8899")
    result = verify_graph(rpc, graph)
    with open(os.environ["TOKEN_GRAPH_VERIFICATION_REPORT"], "w") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != "cycles"}, indent=2))

if __name__ == "__main__":
    main()
