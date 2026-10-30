"""Fail-closed eligibility boundary between research registry and usable pools.

Research-only evidence screen, NOT an on-chain authorization or an SDK auditor.
Signed provenance is a prior acceptance claim; the independent original auditors
must establish it. Every candidate MUST subsequently pass fresh on-chain state,
fee, liquidity and quote checks before the existing coordinator can use it.
Legacy accepted venues require an explicit independently audited evidence bridge.
"""
from collections import Counter

SIX_VENUES = frozenset(("orca", "meteora_damm_v2", "raydium_cpmm",
                        "pumpswap", "meteora_dlmm", "raydium_clmm"))
STATUSES = {
    "pumpswap": "INDEPENDENT_SIGNED_NATIVE_SDK_SPL_PARITY",
    "meteora_dlmm": "INDEPENDENT_DLMM_SIGNED_NATIVE_SDK_SPL_PARITY",
    "raydium_clmm": "INDEPENDENT_CLMM_SIGNED_NATIVE_SDK_SPL_PARITY",
}
LEGACY = SIX_VENUES - STATUSES.keys()


def screen_signed_provenance(registry):
    """Return potential usable identities, never an executable route.

    Does NOT certify SHA digests by itself, replay archived source state,
    or silently equate a historical registered identity to signed acceptance.
    """
    if not isinstance(registry, dict) or not isinstance(registry.get("pools"), list):
        raise ValueError("malformed shared registry")
    entries = registry["pools"]
    if len(entries) > 200:
        raise ValueError("unbounded registry")
    accepted, blocked = [], []
    seen = set()
    for row in entries:
        if not isinstance(row, dict):
            raise ValueError("malformed registry row")
        venue, address = row.get("venue"), row.get("address")
        if venue not in SIX_VENUES or not isinstance(address, str) or not address:
            blocked.append({"venue":venue,"address":address,"reason":"OUT_OF_SCOPE_OR_INVALID"})
            continue
        key = (venue,address)
        if key in seen:
            raise ValueError("duplicate shared registry identity")
        seen.add(key)
        if venue in LEGACY:
            blocked.append({"venue":venue,"address":address,
                            "reason":"LEGACY_SIGNED_EVIDENCE_BRIDGE_REQUIRED"})
            continue
        proof = row.get("signed_provenance")
        if not isinstance(proof, dict) or proof.get("status") != STATUSES[venue]:
            blocked.append({"venue":venue,"address":address,"reason":"SIGNED_PROVENANCE_ABSENT"})
            continue
        hashes = proof.get("signed_transaction_hashes")
        mints = row.get("mints")
        digest = proof.get("source_digest")
        receipt = proof.get("independent_receipt_sha256")
        if (not isinstance(mints, list) or len(mints)!=2 or
            any(not isinstance(m,str) or not m for m in mints) or mints[0]==mints[1] or
            type(proof.get("source_slot")) is not int or proof["source_slot"]<0 or
            not isinstance(hashes,list) or len(hashes)!=4 or
            len(set(map(str,hashes)))!=4 or
            any(type(h) is not str or len(h)!=64 or
                any(c not in "0123456789abcdef" for c in h) for h in hashes) or
            any(type(h) is not str or len(h)!=64 or
                any(c not in "0123456789abcdef" for c in h) for h in (digest,receipt))):
            blocked.append({"venue":venue,"address":address,"reason":"MALFORMED_SIGNED_EVIDENCE"})
            continue
        accepted.append({"venue":venue,"address":address,"mints":list(mints),
                         "source_slot":proof["source_slot"],
                         "signed_provenance_receipt_sha256":receipt,
                         "current_state_verified":False,
                         "current_quote_verified":False,
                         "coordinator_eligible":False})
    return {"status":"HISTORICAL_SIGNED_PROVENANCE_SCREEN_ONLY",
            "candidate_count":len(accepted),"blocked_count":len(blocked),
            "candidates":accepted,"blocked":blocked,
            "coordinator_eligible_count":0,
            "actionable":False,"live_execution_approved":False,"broadcast":False}
