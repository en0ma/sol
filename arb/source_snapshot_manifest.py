"""Deterministic source account manifest; integrity check, NOT chain authentication.

A hash records exact captured bytes and contextual slot but cannot prove the
RPC supplied authentic data. Never confuse this with protocol quote evidence.
"""
import hashlib,json
def digest(accounts,addresses,slot):
    if type(slot)is not int or slot<0 or not isinstance(accounts,dict) or not isinstance(addresses,list) or len(addresses)!=len(set(addresses)) or not addresses:
        raise ValueError("invalid contextual manifest inventory")
    if any(not isinstance(key,str) or not key or key not in accounts for key in addresses):
        raise ValueError("manifest source account missing")
    ordered={key:accounts[key] for key in sorted(addresses)}
    encoded=json.dumps({"slot":slot,"accounts":ordered},sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()
def verify(fixture):
    keys=fixture.get("state_account_addresses")
    slot=fixture.get("state_accounts_observed_slot")
    claimed=fixture.get("state_account_manifest_sha256")
    if not isinstance(claimed,str) or len(claimed)!=64 or digest(fixture.get("accounts"),keys,slot)!=claimed:
        raise ValueError("source state manifest checksum mismatch")
    return True
