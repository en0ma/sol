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
    fee_payers=set()
    payer_balances=set()
    payer=str(tx.message.account_keys[0])
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
            or row.get("confirmed_transaction") is not True
            or row.get("fee_payer")!=payer
            or type(row.get("fee_payer_pre_lamports")) is not int
            or type(row.get("fee_payer_post_lamports")) is not int
            or not row["fee_lamports"]<=row["fee_payer_pre_lamports"]<2**64
            or not 0<=row["fee_payer_post_lamports"]<2**64):
            raise ValueError("signed receipt identity, status or fee mismatch")
        fees.add(row["fee_lamports"])
        slots.add(row["slot"])
        fee_payers.add(row["fee_payer"])
        payer_balances.add((row["fee_payer_pre_lamports"],
                            row["fee_payer_post_lamports"]))
    if len(fees)!=1 or len(slots)!=1 or len(fee_payers)!=1 or len(payer_balances)!=1:
        raise ValueError("independent fee observations disagree")
    return {"status":"TWO_RPC_RECORDED_FEE_CORROBORATION_NO_TRUST_ROOT",
            "signed_packet_sha256":fingerprint,
            "first_signature":signature,
            "observed_fee_lamports":next(iter(fees)),
            "observed_slot":next(iter(slots)),
            "fee_payer":payer,
            "fee_payer_pre_post_lamports":list(next(iter(payer_balances))),
            "fee_payer_balance_change_is_not_fee_only":True,
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
    pre=meta.get("preBalances")
    post=meta.get("postBalances")
    if (not isinstance(pre,list) or not isinstance(post,list) or
        len(pre)!=len(post) or not pre or
        any(type(n)is not int or not 0<=n<2**64 for n in pre+post)):
        raise ValueError("remote fee payer pre/post balance evidence unavailable")
    return {"rpc_url":rpc,"signature":signature,
            "fee_payer":str(tx.message.account_keys[0]),
            "fee_payer_pre_lamports":pre[0],
            "fee_payer_post_lamports":post[0],
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

def quote_signed_message_fee_two_read_only_observers(rpc_a, rpc_b, signed_wire):
    """Corroborate getFeeForMessage for the exact verified signed message.

    These are *quotes* from two HTTPS RPC providers, never an observed paid
    fee. On-chain transaction fees depend on signatures, budget/priority
    instructions and blockhash context. No transaction submission occurs.
    """
    from arb.rpc import call
    from solders.transaction import VersionedTransaction
    urls=(rpc_a,rpc_b)
    hosts=[]
    for rpc in urls:
        if not isinstance(rpc,str):
            raise ValueError("explicit independent RPC URLs required")
        parsed=urlsplit(rpc)
        if (parsed.scheme!="https" or not parsed.hostname or
            parsed.username or parsed.password or parsed.fragment or
            parsed.hostname in ("localhost","127.0.0.1","::1")):
            raise ValueError("read-only remote HTTPS fee source required")
        hosts.append(parsed.hostname)
    if hosts[0]==hosts[1]:
        raise ValueError("same RPC provider cannot corroborate fee quote")
    if not isinstance(signed_wire,bytes) or not 0<len(signed_wire)<=1232:
        raise ValueError("bounded signed packet required")
    try:
        tx=VersionedTransaction.from_bytes(signed_wire)
        tx.verify_and_hash_message()
        if not tx.signatures:
            raise ValueError("unsigned transaction")
        message=bytes(tx.message)
    except Exception as exc:
        raise ValueError("signed transaction cryptographic verification failed") from exc
    quoted=[];slots=[]
    encoded=base64.b64encode(message).decode("ascii")
    for rpc in urls:
        result=call(rpc,"getFeeForMessage",[
            encoded,{"commitment":"confirmed"}])
        fee=result.get("value") if isinstance(result,dict) else None
        slot=result.get("context",{}).get("slot") if isinstance(result,dict) else None
        if (type(fee)is not int or not 0<=fee<2**64
            or type(slot)is not int or slot<0):
            raise ValueError("unavailable or malformed signed message fee quote")
        quoted.append(fee)
        slots.append(slot)
    if quoted[0]!=quoted[1]:
        raise ValueError("independent fee quotes disagree")
    return {"status":"TWO_RPC_SIGNED_MESSAGE_FEE_QUOTE_NOT_PAID_SPEND",
            "message_sha256":hashlib.sha256(message).hexdigest(),
            "signed_packet_sha256":hashlib.sha256(signed_wire).hexdigest(),
            "first_signature":str(tx.signatures[0]),
            "quoted_fee_lamports":quoted[0],
            "quote_context_slots":slots,
            "remote_provider_count":2,
            "independent_provider_ownership_proven":False,
            "independent_paid_fee_verified":False,
            "net_profitability_verified":False,**SAFE}
