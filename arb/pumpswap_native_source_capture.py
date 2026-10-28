"""Fourth-venue PumpSwap read-only authenticated source capture.

This is a research-stage capture, not native-price parity, signing, registry
admission, or authorization for live execution. Only reused registry hints.
"""
import argparse
import base64
import json
import hashlib
from pathlib import Path

from arb.pumpswap_pool import PROGRAM, decode, verify
from arb.rpc import call

SAFE = {"actionable": False, "broadcast": False,
        "signed_parity_verified": False, "native_pricing_verified": False,
        "registry_admission_approved": False}


def capture(rpc, registry, *, limit=3):
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError("invalid bounded PumpSwap research sample")
    if not isinstance(registry, dict) or not isinstance(registry.get("pools"), list):
        raise ValueError("pool registry unavailable")
    addresses = []
    seen = set()
    for item in registry["pools"]:
        if not isinstance(item, dict) or item.get("venue") != "pumpswap":
            continue
        address = item.get("address")
        if not isinstance(address, str) or not 32 <= len(address) <= 44 or address in seen:
            continue
        seen.add(address)
        addresses.append((address, item.get("mints")))
        if len(addresses) == limit:
            break
    if len(addresses) < limit:
        raise ValueError("insufficient registered PumpSwap identity hints")
    results = []
    for address, expected_mints in addresses:
        try:
            response = call(rpc, "getAccountInfo", [address, {
                "encoding": "base64", "commitment": "confirmed"}])
            info = response.get("value")
            slot = response.get("context", {}).get("slot")
            if (type(slot) is not int or slot < 0 or
                    not isinstance(info, dict) or info.get("owner") != PROGRAM or
                    info.get("executable") is not False or
                    info.get("data", [None, None])[1] != "base64"):
                raise ValueError("PumpSwap source pool owner/slot/data invalid")
            raw = base64.b64decode(info["data"][0], validate=True)
            state = decode(raw)
            if expected_mints is not None and (
                    not isinstance(expected_mints, list) or
                    len(expected_mints) != 2 or
                    set(expected_mints) != {state["base_mint"], state["quote_mint"]}):
                raise ValueError("tracked pool mint identity mismatch")
            verified = verify(rpc, address, state, include_source_bytes=True)
            if verified.get("verified") is not True:
                raise ValueError("on-chain pool verifier rejected source")
            source_accounts=verified.get("authenticated_source_accounts")
            if not isinstance(source_accounts,list) or len(source_accounts)!=6:
                raise ValueError("incomplete authenticated same-slot source account bundle")
            if source_accounts[0].get("address")!=address:
                raise ValueError("authenticated source bundle pool mismatch")
            verified_slot=verified.get("slot")
            if type(verified_slot) is not int or verified_slot<0:
                raise ValueError("missing verifier snapshot slot")
            if len({a.get("address") for a in source_accounts})!=6:
                raise ValueError("duplicate authenticated source account")
            for account in source_accounts:
                if (not isinstance(account.get("address"),str)
                        or not isinstance(account.get("owner"),str)
                        or not isinstance(account.get("account_base64"),str)):
                    raise ValueError("invalid authenticated source account")
                base64.b64decode(account["account_base64"],validate=True)
            # Digest binds exact bytes, identities, owners and source-slot context.
            source_digest=hashlib.sha256(json.dumps({
                "slot":verified_slot,"accounts":source_accounts
            },sort_keys=True,separators=(",",":")).encode()).hexdigest()
            # Candidate quotes are research evidence, NEVER signed trial receipts.
            # Both directions and two distinct sizes reveal unsupported fee modes
            # before investing in an isolated swap harness.
            from arb.pumpswap_native_candidate import quote_exact_input
            candidates=[]
            for mint_in in (state["base_mint"],state["quote_mint"]):
                for size in (10_000,100_000):
                    try:
                        candidate=quote_exact_input(verified,mint_in,size)
                        candidates.append(candidate)
                    except (ValueError,KeyError,TypeError) as exc:
                        candidates.append({"mint_in":mint_in,"amount_in":size,
                                           "status":"NATIVE_CANDIDATE_BLOCKED",
                                           "reason":str(exc)[:160],
                                           "actionable":False,"signed_parity_verified":False})
            results.append({"address": address, "status": "AUTHENTICATED_SOURCE_ONLY",
                            "pool_account_slot": slot,
                            "verified_snapshot_slot": verified_slot,
                            "authenticated_source_sha256": source_digest,
                            "mints": [state["base_mint"], state["quote_mint"]],
                            "source_pool_base64": source_accounts[0]["account_base64"],
                            "authenticated_source_accounts": source_accounts,
                            "source_fee_mode": verified["fee_mode_diagnostic"]["status"],
                            "native_quote_candidates": candidates,
                            "effective_fee_verified": False,
                            "signed_parity_verified": False})
        except (ValueError, KeyError, TypeError, RuntimeError, OSError) as exc:
            results.append({"address": address, "status": "SOURCE_REJECTED",
                            "reason": str(exc)[:200]})
    return {"venue": "pumpswap", "status": "RESEARCH_SOURCE_CAPTURE_ONLY",
            "requested": limit, "authenticated": sum(
                x["status"] == "AUTHENTICATED_SOURCE_ONLY" for x in results),
            "pools": results, **SAFE}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpc", required=True)
    parser.add_argument("--registry", default="arb/pool_registry.json")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = capture(args.rpc, json.loads(Path(args.registry).read_text()), limit=args.limit)
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("venue", "status", "requested", "authenticated")}))
    if result["authenticated"] != args.limit:
        raise SystemExit("PumpSwap source capture incomplete; not eligible for pricing")


if __name__ == "__main__":
    main()
