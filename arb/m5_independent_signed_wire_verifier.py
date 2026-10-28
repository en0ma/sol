"""Independently authenticate bytes of the signed positive and negative Surfpool packets.

A receipt's claimed signature, SHA-256, and packet length are NOT cryptographic
evidence until bound to actual signed Solana wire bytes. Parse and verify both
transactions with solders, then compare signer keys and recent blockhash. No
connection to a live RPC endpoint or broadcast method exists in this module.
"""
import base64
import hashlib
from solders.transaction import VersionedTransaction
from solders.message import to_bytes_versioned

SAFETY={"actionable":False,"broadcast":False,"live_execution_approved":False}

def _packet(receipt,prefix):
    if prefix=="positive":
        encoded=receipt.get("signed_transaction_wire_base64")
        digest=receipt.get("signed_transaction_sha256")
        signature=receipt.get("signed_transaction_signature")
        size=receipt.get("signed_packet_bytes")
    elif prefix=="negative":
        encoded=receipt.get("negative_signed_transaction_wire_base64")
        digest=receipt.get("negative_signed_transaction_sha256")
        signature=receipt.get("negative_signed_transaction_signature")
        size=receipt.get("negative_packet_bytes")
    else:
        raise ValueError("unsupported signed packet role")
    if (not isinstance(encoded,str) or len(encoded)>2048 or
            not isinstance(digest,str) or len(digest)!=64 or
            not isinstance(signature,str) or
            type(size)is not int or not 100<=size<=1232):
        raise ValueError(prefix+" signed packet bytes, signature or size missing")
    try:
        raw=base64.b64decode(encoded,validate=True)
    except (ValueError,base64.binascii.Error) as exc:
        raise ValueError(prefix+" signed wire encoding invalid") from exc
    if len(raw)!=size or hashlib.sha256(raw).hexdigest()!=digest:
        raise ValueError(prefix+" signed wire digest or packet size mismatch")
    try:
        tx=VersionedTransaction.from_bytes(raw)
        tx.verify_and_hash_message()
    except Exception as exc:
        raise ValueError(prefix+" packet signature verification failed") from exc
    signatures=tx.signatures
    if not signatures or str(signatures[0])!=signature:
        raise ValueError(prefix+" signed fee-payer signature mismatch")
    account_keys=tx.message.account_keys
    if not account_keys or not hasattr(tx.message,"recent_blockhash"):
        raise ValueError(prefix+" missing signed fee payer or recent blockhash")
    message_sha256=hashlib.sha256(to_bytes_versioned(tx.message)).hexdigest()
    return {"packet_sha256":digest,"packet_length":size,
            "message_sha256":message_sha256,
            "fee_payer":str(account_keys[0]),
            "recent_blockhash":str(tx.message.recent_blockhash),
            "signature":signature,"transaction":tx}

def verify_signed_pair(receipt):
    if (not isinstance(receipt,dict) or
            any(receipt.get(k)is not False for k in SAFETY)):
        raise ValueError("only nonbroadcast signed local simulation evidence accepted")
    pos=_packet(receipt,"positive")
    neg=_packet(receipt,"negative")
    if pos["packet_sha256"]==neg["packet_sha256"] or pos["signature"]==neg["signature"]:
        raise ValueError("negative packet reuses positive signed message")
    if pos["fee_payer"]!=neg["fee_payer"]:
        raise ValueError("negative control signed by a different fee payer")
    if pos["recent_blockhash"]!=neg["recent_blockhash"]:
        raise ValueError("positive and negative transaction were not signed for the same fork blockhash")
    fee=receipt.get("signed_message_fee_estimate")
    if fee is not None:
        if not isinstance(fee,dict) or any(
                fee.get(key)is not False for key in SAFETY):
            raise ValueError("signed fee quote has unsafe provenance")
        if fee.get("status")=="SIGNED_MESSAGE_FEE_ESTIMATE_ONLY":
            if (fee.get("signed_message_sha256")!=pos["message_sha256"] or
                    fee.get("fee_payer_asset")!="SOL" or
                    type(fee.get("estimated_fee_lamports"))is not int or
                    fee["estimated_fee_lamports"]<0 or
                    fee.get("paid_fee_verified") is not False):
                raise ValueError("fee estimate does not belong to signed positive message")
        elif fee.get("status")!="FEE_ESTIMATE_UNAVAILABLE":
            raise ValueError("unrecognized signed-message fee provenance")
    count=receipt.get("legs")
    instructions_pos=pos["transaction"].message.instructions
    instructions_neg=neg["transaction"].message.instructions
    if (type(count)is not int or not 2<=count<=6
            or len(instructions_pos)!=count or len(instructions_neg)!=count):
        raise ValueError("signed positive and negative transaction leg count mismatch")
    # The negative control must replay precisely the same signed first N-1
    # compiled swaps. The last swap alone changes to induce failure and
    # establish rollback. This is verified from actual signed message bytes.
    if any(bytes(a)!=bytes(b) for a,b in zip(
            instructions_pos[:-1],instructions_neg[:-1])):
        raise ValueError("negative signed control changed an earlier swap")
    if bytes(instructions_pos[-1])==bytes(instructions_neg[-1]):
        raise ValueError("negative signed control did not change final swap")

    return {"status":"CRYPTOGRAPHICALLY_VERIFIED_INDEPENDENT_SIGNED_PACKET_PAIR",
            "positive_sha256":pos["packet_sha256"],
            "negative_sha256":neg["packet_sha256"],
            "signed_message_fee_digest_bound":(
                isinstance(fee,dict) and
                fee.get("status")=="SIGNED_MESSAGE_FEE_ESTIMATE_ONLY"),
            "same_signer_and_blockhash_verified":True,
            "signed_prefix_instructions_identical_verified":True,
            "signed_final_instruction_changed_verified":True,
            "positive_signed_message_verified":True,
            "negative_signed_message_verified":True,
            "signed_wire_packet_sizes":[pos["packet_length"],neg["packet_length"]],
            "protocol_exact_quote_verified":False,
            "net_profit_verified":False,**SAFETY}
