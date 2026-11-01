"""Read-only independent *corroboration* of recorded signed-transaction fees.

An offline simulation is not a paid transaction. An independently fetched
historical confirmed transaction can demonstrate a recorded fee *observation*,
but not prove an independent trust root merely from two RPC URLs. No writes.
"""
import base64
import hashlib
from urllib.parse import urlsplit

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def corroborate_signed_fee_receipts(wire, observations):
    """Require two byte-identical, independently queried RPC receipts.

    Cross-endpoint agreement is useful evidence, not independent finality.
    The signer must check trusted RPC operators externally.
    """
    from solders.transaction import VersionedTransaction
    if not isinstance(wire,bytes) or not 0<len(wire)<=1232:
        raise ValueError("signed transaction bytes required")
    try:
        tx=VersionedTransaction.from_bytes(wire)
        tx.verify_and_hash_message()
    except Exception as exc:
        raise ValueError("signed wire verification failed") from exc
    if not tx.signatures or not isinstance(observations,list) or len(observations)!=2:
        raise ValueError("two independent recorded observations required")
    signature=str(tx.signatures[0])
    fingerprint=hashlib.sha256(wire).hexdigest()
    distinct=set()
    fees=set()
    slots=set()
    for row in observations:
        if not isinstance(row,dict):
            raise ValueError("invalid fee observation")
        url=row.get("rpc_url")
        parsed=urlsplit(url) if isinstance(url,str) else None
        if (parsed is None or parsed.scheme!="https" or not parsed.hostname
            or parsed.username or parsed.password or parsed.fragment
            or parsed.hostname in ("localhost","127.0.0.1","::1")
            or parsed.hostname in distinct):
            raise ValueError("two distinct trusted HTTPS observers required")
        distinct.add(parsed.hostname)
        if (row.get("signature")!=signature
            or row.get("wire_sha256")!=fingerprint
            or row.get("err") is not None
            or type(row.get("fee_lamports")) is not int
            or not 0<=row["fee_lamports"]<2**64
            or type(row.get("slot")) is not int or row["slot"]<0
            or row.get("confirmed_transaction") is not True):
            raise ValueError("signed receipt identity, status or fee mismatch")
        fees.add(row["fee_lamports"])
        slots.add(row["slot"])
    if len(fees)!=1 or len(slots)!=1:
        raise ValueError("independent fee observations disagree")
    return {"status":"TWO_RPC_RECORDED_FEE_CORROBORATION_NO_TRUST_ROOT",
            "signed_packet_sha256":fingerprint,
            "first_signature":signature,
            "observed_fee_lamports":next(iter(fees)),
            "observed_slot":next(iter(slots)),
            "rpc_observers_count":2,
            "upstream_independence_cryptographically_proven":False,
            "actual_mainnet_fee_payer_spend_independently_proven":False,
            "simulation_network_fee_paid":False,
            "net_profitability_verified":False,**SAFE}

def fetch_confirmed_fee_observation(rpc, wire):
    """Read exact signed wire and fee from a remote confirmed transaction."""
    from solders.transaction import VersionedTransaction
    from arb.rpc import call
    parsed=urlsplit(rpc)
    if (parsed.scheme!="https" or not parsed.hostname or
        parsed.username or parsed.password or parsed.fragment or
        parsed.hostname in ("localhost","127.0.0.1","::1") or
        not isinstance(wire,bytes) or not 0<len(wire)<=1232):
        raise ValueError("HTTPS remote transaction read required")
    try:
        tx=VersionedTransaction.from_bytes(wire)
        tx.verify_and_hash_message()
        signature=str(tx.signatures[0])
    except Exception as exc:
        raise ValueError("bad original signed transaction") from exc
    receipt=call(rpc,"getTransaction",[signature,{"encoding":"base64",
                 "commitment":"confirmed","maxSupportedTransactionVersion":0}])
    if not isinstance(receipt,dict) or not isinstance(receipt.get("meta"),dict):
        raise ValueError("remote signed transaction unavailable")
    encoded=receipt.get("transaction")
    if (not isinstance(encoded,list) or len(encoded)!=2 or encoded[1]!="base64"
        or not isinstance(encoded[0],str)):
        raise ValueError("recorded wire bytes unavailable")
    try:
        actual=base64.b64decode(encoded[0],validate=True)
    except (ValueError,base64.binascii.Error) as exc:
        raise ValueError("invalid recorded wire encoding") from exc
    if actual!=wire:
        raise ValueError("remote recorded signed wire not identical")
    meta=receipt["meta"]
    return {"rpc_url":rpc,"signature":signature,
            "wire_sha256":hashlib.sha256(wire).hexdigest(),
            "slot":receipt.get("slot"),"fee_lamports":meta.get("fee"),
            "err":meta.get("err"),"confirmed_transaction":True}

def inspect_fee_two_read_only_observers(rpc_a, rpc_b, signed_wire):
    """Fetch both confirmed receipts directly; do not trust supplied reports.

    HTTPS hosts are only a weak proxy for different infrastructure. This
    remains corroborated RPC evidence, not cryptographic proof of settlement.
    """
    hosts=[]
    for rpc in (rpc_a,rpc_b):
        if not isinstance(rpc,str):
            raise ValueError("two explicit RPC URLs required")
        parsed=urlsplit(rpc)
        if (parsed.scheme!="https" or not parsed.hostname
            or parsed.username or parsed.password or parsed.fragment
            or parsed.hostname in ("localhost","127.0.0.1","::1")):
            raise ValueError("two independently supplied HTTPS endpoints required")
        hosts.append(parsed.hostname)
    if hosts[0]==hosts[1]:
        raise ValueError("same remote source cannot independently corroborate itself")
    first=fetch_confirmed_fee_observation(rpc_a,signed_wire)
    second=fetch_confirmed_fee_observation(rpc_b,signed_wire)
    return corroborate_signed_fee_receipts(signed_wire,[first,second])
