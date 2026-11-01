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
