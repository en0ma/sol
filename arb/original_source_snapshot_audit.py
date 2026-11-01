"""Bind original upstream source accounts to a single observed slot.

This validates content integrity, owner and snapshot consistency; the RPC
operator is NOT cryptographically authenticated merely by HTTPS or hashes.
"""
import base64
import hashlib
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
def inspect_original_source_batch(snapshot, identities, *, required_slot=None):
    if (not isinstance(snapshot,dict) or not isinstance(identities,list)
        or not 1<=len(identities)<=128
        or (required_slot is not None and
            (type(required_slot)is not int or required_slot<0))):
        raise ValueError("bounded snapshot and account identities required")
    slot=snapshot.get("context",{}).get("slot")
    rows=snapshot.get("value")
    if (type(slot)is not int or slot<0
        or required_slot is not None and slot<required_slot
        or not isinstance(rows,list) or len(rows)!=len(identities)):
        raise ValueError("original RPC context or ordering mismatch")
    seen=set()
    checked=[]
    for identity,account in zip(identities,rows):
        if (not isinstance(identity,dict) or
            not isinstance(identity.get("address"),str) or
            not isinstance(identity.get("owner"),str) or
            identity["address"] in seen or
            not isinstance(account,dict) or
            account.get("owner")!=identity["owner"] or
            account.get("executable") is not False or
            not isinstance(account.get("data"),list) or
            len(account["data"])!=2 or
            account["data"][1]!="base64"):
            raise ValueError("source account owner, address, or encoding mismatch")
        seen.add(identity["address"])
        raw=base64.b64decode(account["data"][0],validate=True)
        if not raw or len(raw)>4_194_304:
            raise ValueError("empty or oversized original account")
        digest=hashlib.sha256(raw).hexdigest()
        expected=identity.get("sha256")
        if expected is not None and digest!=expected:
            raise ValueError("original account expected digest mismatch")
        checked.append({"address":identity["address"],"owner":identity["owner"],
                        "sha256":digest,"source_slot":slot,"length":len(raw)})
    return {"status":"SAME_SLOT_ORIGINAL_RPC_BYTES_AND_OWNERS_CHECKED",
            "source_slot":slot,"accounts":checked,
            "upstream_rpc_operator_trust_independently_proven":False,
            "upstream_consensus_finality_proven":False,**SAFE}

def corroborate_original_source_batches(first, second, identities, *,
                                        required_slot=None):
    """Compare separately captured original-account bytes at the exact slot.

    This is a cross-observer integrity boundary, not an authenticated Solana
    bank root. In particular two RPC hosts may collude or share upstreams.
    Consumers MUST NOT change the trust/finality flags using this report.
    """
    a=inspect_original_source_batch(first,identities,required_slot=required_slot)
    b=inspect_original_source_batch(second,identities,required_slot=required_slot)
    if a["source_slot"]!=b["source_slot"]:
        raise ValueError("original account snapshots are not same-slot")
    if a["accounts"]!=b["accounts"]:
        raise ValueError("original account bytes, order or owners disagree")
    return {"status":"TWO_OBSERVER_SAME_SLOT_ORIGINAL_ACCOUNT_CORROBORATION",
            "source_slot":a["source_slot"],
            "account_count":len(a["accounts"]),
            "accounts":a["accounts"],
            "cross_observer_byte_agreement":True,
            "independent_operator_ownership_proven":False,
            "solana_bank_hash_cryptographically_verified":False,
            "upstream_rpc_operator_trust_independently_proven":False,
            "upstream_consensus_finality_proven":False,**SAFE}


def capture_original_source_two_observers(rpc_a, rpc_b, identities, *,
                                          required_slot=None):
    """Read immutable original account data from two HTTPS RPC endpoints.

    Each provider is asked for a single getMultipleAccounts snapshot at a
    confirmed commitment. The second provider is required to return the same
    slot (minContextSlot is merely a floor, not an exact-slot request).
    A disagreement is rejected; it is never resolved by choosing one host.
    There is no write, local signing or mainnet transaction submission.
    """
    from urllib.parse import urlsplit
    from arb.rpc import call
    if not isinstance(identities,list) or not 1<=len(identities)<=128:
        raise ValueError("bounded account manifest required")
    if any(not isinstance(i,dict) or not isinstance(i.get("address"),str)
           or not i["address"] for i in identities):
        raise ValueError("invalid account manifest")
    hosts=[]
    for rpc in (rpc_a,rpc_b):
        if not isinstance(rpc,str):
            raise ValueError("explicit HTTPS source endpoints required")
        url=urlsplit(rpc)
        if (url.scheme!="https" or not url.hostname
            or url.username or url.password or url.fragment
            or url.hostname in ("localhost","127.0.0.1","::1")
            or url.port==8899):
            raise ValueError("original source must use remote HTTPS")
        hosts.append(url.hostname)
    if hosts[0]==hosts[1]:
        raise ValueError("two different source hostnames required")
    options={"encoding":"base64","commitment":"confirmed"}
    if required_slot is not None:
        if type(required_slot)is not int or required_slot<0:
            raise ValueError("invalid source slot floor")
        options["minContextSlot"]=required_slot
    addresses=[i["address"] for i in identities]
    first=call(rpc_a,"getMultipleAccounts",[addresses,options])
    first_audit=inspect_original_source_batch(
        first,identities,required_slot=required_slot)
    second_options={**options,"minContextSlot":first_audit["source_slot"]}
    second=call(rpc_b,"getMultipleAccounts",[addresses,second_options])
    return corroborate_original_source_batches(
        first,second,identities,required_slot=required_slot)
