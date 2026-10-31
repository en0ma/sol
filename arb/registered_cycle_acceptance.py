"""Fail-closed four-gate acceptance screen for signed offline circular routes.

This is an evidence boundary, not a fee oracle or an executable coordinator.
Authenticity cannot be manufactured from self-attested JSON. Source RPC,
signed SPL receipt and actual fee-payer evidence must be independently audited.
"""
import hashlib
from arb.atomic_graph_coordinator import observed_registered_signed_cycle_economics
from arb.six_venue_route_economics import WRAPPED_SOL_MINT, UINT64

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}


def verify_original_account_snapshot(account, original_bytes, *, expected_owner,
                                     expected_address, expected_slot, expected_sha256):
    """Check original-account identity and bytes; do not claim RPC trust."""
    if (not isinstance(account,dict) or type(original_bytes)is not bytes
        or not 0<len(original_bytes)<=4_194_304
        or type(expected_address)is not str or not expected_address
        or type(expected_owner)is not str or not expected_owner
        or type(expected_slot)is not int or expected_slot<0
        or type(expected_sha256)is not str or len(expected_sha256)!=64):
        raise ValueError("original account evidence incomplete")
    digest=hashlib.sha256(original_bytes).hexdigest()
    if (digest!=expected_sha256 or account.get("address")!=expected_address
        or account.get("owner")!=expected_owner
        or type(account.get("slot"))is not int or account["slot"]!=expected_slot
        or type(account.get("lamports"))is not int
        or not 0<=account["lamports"]<UINT64
        or account.get("executable") is not False):
        raise ValueError("original account identity, slot, or digest mismatch")
    # The auditor must independently establish original RPC origin, token
    # mints and vault bindings. A digest/owner match alone cannot prove them.
    return {"status":"ORIGINAL_ACCOUNT_CONTENT_IDENTITY_ONLY",
            "account_address":expected_address,"account_owner":expected_owner,
            "source_slot":expected_slot,"source_sha256":digest,
            "upstream_origin_independently_authenticated":False,**SAFE}


def screen_signed_cycle_net_acceptance(route, signed_receipt, local_fee,
                                       *, source_accounts, fee_components=None):
    """Combine four gates without converting untrusted claims to acceptance.

    If all independent receipts are eventually supplied, implement the
    external independent signer/fee auditor first; this screen never promotes
    a locally recorded fee to real fee expenditure.
    """
    gross=observed_registered_signed_cycle_economics(route,signed_receipt)
    gates={"original_source_authenticated":False,
           "signed_execution_and_spl_rollback":
               gross.get("status")=="SIGNED_ROUTE_GROSS_ONLY_NETWORK_COST_UNKNOWN",
           "complete_actual_fee_accounting":False,
           "positive_net_cycle_independently_accepted":False}
    if not isinstance(source_accounts,list) or not 2<=len(source_accounts)<=6:
        raise ValueError("bounded original account evidence required")
    identities=[]
    seen=set()
    slots=set()
    for row in source_accounts:
        if (not isinstance(row,dict) or
            row.get("status")!="ORIGINAL_ACCOUNT_CONTENT_IDENTITY_ONLY" or
            row.get("upstream_origin_independently_authenticated") is not False or
            any(row.get(k) is not False for k in SAFE) or
            type(row.get("source_slot"))is not int or row["source_slot"]<0 or
            type(row.get("source_sha256"))is not str or
            len(row["source_sha256"])!=64 or
            not isinstance(row.get("account_address"),str) or
            not row["account_address"] or row["account_address"] in seen):
            raise ValueError("untrusted original-account inventory")
        seen.add(row["account_address"])
        slots.add(row["source_slot"])
        identities.append(row["account_address"])
    if len(slots)!=1:
        raise ValueError("cross-slot original account snapshots unsupported")
    legs=route.get("legs") if isinstance(route,dict) else None
    if (not isinstance(legs,list) or len(legs)!=len(identities) or
        any(not isinstance(leg,dict) or leg.get("pool")!=identities[i]
            for i,leg in enumerate(legs))):
        raise ValueError("original source accounts must match route legs in order")
    if not isinstance(local_fee,dict) or local_fee.get("status")!=(
        "LOCAL_FEE_EVIDENCE_CORRELATED_NOT_AUTHENTICATED") or (
        local_fee.get("independent_fee_paid_verified") is not False or
        local_fee.get("fee_lamports") is not None or
        any(local_fee.get(k) is not False for k in SAFE)):
        raise ValueError("independent paid-fee evidence missing")
    if fee_components is not None:
        if (not isinstance(fee_components,dict) or
            set(fee_components)!={"network_fee","priority_fee",
                                  "setup_rent_net","flash_loan_fee","tip","other"} or
            any(type(v)is not int or not 0<=v<UINT64
                for v in fee_components.values())):
            raise ValueError("malformed complete-cost candidate")
    # Candidate costs are retained for diagnostics only; never inferred as
    # paid from local fee metadata, even when they appear net positive.
    observed=gross.get("gross_start_mint_base_units")
    candidate_total=sum(fee_components.values()) if fee_components is not None else None
    return {"status":"CYCLE_ACCEPTANCE_BLOCKED_INDEPENDENT_SOURCE_AND_FEES",
            "route_legs":len(route.get("legs",[])) if isinstance(route,dict) else None,
            "source_account_count":len(identities),
            "source_slot_content_consistent":True,
            "observed_signed_gross_base_units":observed,
            "candidate_fee_total_base_units_unverified":candidate_total,
            "candidate_net_base_units_unverified":
                (observed-candidate_total if type(observed)is int and
                 candidate_total is not None and candidate_total<UINT64 else None),
            "accepted_net_profit_base_units":None,
            "net_profitability_verified":False,
            "gates":gates,**SAFE}


def inspect_upstream_original_account(rpc, *, address, expected_owner,
                                      min_context_slot=0):
    """Read original upstream account bytes with slot and owner checks.

    Caller must configure its independently trusted *read-only* upstream RPC.
    A single endpoint cannot prove independence, pool vaults, or fresh parity.
    """
    import base64
    from urllib.parse import urlsplit
    from arb.rpc import call
    parsed=urlsplit(rpc)
    if (parsed.scheme!="https" or not parsed.hostname or
        parsed.username or parsed.password or parsed.fragment or
        parsed.hostname in ("localhost","127.0.0.1","::1") or
        not isinstance(address,str) or not address or
        not isinstance(expected_owner,str) or not expected_owner or
        type(min_context_slot)is not int or min_context_slot<0):
        raise ValueError("independent upstream HTTPS read-only account source required")
    result=call(rpc,"getAccountInfo",[address,{
        "encoding":"base64","commitment":"confirmed",
        "minContextSlot":min_context_slot}])
    if (not isinstance(result,dict) or not isinstance(result.get("context"),dict) or
        type(result["context"].get("slot"))is not int or
        result["context"]["slot"]<min_context_slot or
        not isinstance(result.get("value"),dict)):
        raise ValueError("missing original upstream account and context")
    row=result["value"]
    data=row.get("data")
    if (not isinstance(data,list) or len(data)!=2 or data[1]!="base64"
        or not isinstance(data[0],str) or
        row.get("owner")!=expected_owner or row.get("executable") is not False or
        type(row.get("lamports"))is not int or not 0<=row["lamports"]<UINT64):
        raise ValueError("original account owner or encoding rejected")
    try:
        original=base64.b64decode(data[0],validate=True)
    except (ValueError,base64.binascii.Error) as exc:
        raise ValueError("invalid upstream account base64") from exc
    if not 0<len(original)<=4_194_304:
        raise ValueError("empty or oversized upstream account")
    digest=hashlib.sha256(original).hexdigest()
    account={"address":address,"owner":row["owner"],
             "slot":result["context"]["slot"],
             "lamports":row["lamports"],"executable":False}
    checked=verify_original_account_snapshot(
        account,original,expected_owner=expected_owner,
        expected_address=address,expected_slot=account["slot"],
        expected_sha256=digest)
    return {**checked,"status":"UPSTREAM_ACCOUNT_RPC_OBSERVED_ORIGIN_UNATTESTED",
            "origin_rpc_hostname":parsed.hostname,
            "original_data_length":len(original),
            "upstream_origin_independently_authenticated":False}
