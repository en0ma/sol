"""Read-only Solana fee-for-message estimate for the EXACT signed simulation message.

This is not a paid fee and does not imply a transaction was broadcast.
No network is used except the caller-provided isolated local Surfpool RPC.
"""
import base64,hashlib
from arb.rpc import call
from arb.pumpswap_local_simulation import local_rpc_only
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def estimate_signed_message_fee(rpc,transaction):
    local_rpc_only(rpc)
    if not hasattr(transaction,"signatures") or not transaction.signatures:
        raise ValueError("signed transaction signatures required")
    # Verify the signed packet itself before attributing a fee quote to it.
    if hasattr(transaction,"verify"):
        transaction.verify()
    # A signed VersionedTransaction serializes MessageV0 with a version prefix.
    # The wire format is required for RPC to resolve v0 lookup account indexes.
    from solders.message import to_bytes_versioned
    msg=to_bytes_versioned(transaction.message)
    if not msg:
        raise ValueError("empty signed message")
    digest=hashlib.sha256(msg).hexdigest()
    try:
        response=call(rpc,"getFeeForMessage",[
            base64.b64encode(msg).decode("ascii"),{"commitment":"processed"}])
    except (ValueError,KeyError,TypeError,RuntimeError,OSError) as exc:
        return {"status":"FEE_ESTIMATE_UNAVAILABLE",
                "signed_message_sha256":digest,"reason":str(exc)[:140],**SAFE}
    # Some JSON-RPC adapters unwrap the result object; others return it
    # under result. Never treat a missing value as a zero fee.
    if isinstance(response,dict) and isinstance(response.get("result"),dict):
        response=response["result"]
    value=response.get("value") if isinstance(response,dict) else None
    if type(value)is not int or value<0:
        return {"status":"FEE_ESTIMATE_UNAVAILABLE",
                "signed_message_sha256":digest,
                "reason":"RPC did not return an integer lamport fee",**SAFE}
    return {"status":"SIGNED_MESSAGE_FEE_ESTIMATE_ONLY",
            "signed_message_sha256":digest,
            "estimated_fee_lamports":value,
            "paid_fee_verified":False,"fee_payer_asset":"SOL",
            "swap_output_debited_for_network_fee":False,
            "source":"getFeeForMessage",
            **SAFE}


def verify_recorded_signed_fee_estimate(transaction,recorded):
    """Bind an RPC fee estimate to the cryptographically checked message.

    The RPC value is recorded evidence, not an independently attested paid fee.
    """
    from solders.message import to_bytes_versioned
    if not isinstance(recorded,dict) or any(recorded.get(k) is not False for k in SAFE):
        raise ValueError("unsafe recorded signed fee estimate")
    expected=hashlib.sha256(to_bytes_versioned(transaction.message)).hexdigest()
    if recorded.get("signed_message_sha256")!=expected:
        raise ValueError("recorded fee estimate message digest mismatch")
    status=recorded.get("status")
    if status=="FEE_ESTIMATE_UNAVAILABLE":
        if recorded.get("estimated_fee_lamports") is not None:
            raise ValueError("unavailable fee estimate contains amount")
        value=None
    elif status=="SIGNED_MESSAGE_FEE_ESTIMATE_ONLY":
        value=recorded.get("estimated_fee_lamports")
        if (type(value) is not int or not 0<=value<2**64
                or recorded.get("paid_fee_verified") is not False
                or recorded.get("swap_output_debited_for_network_fee") is not False
                or recorded.get("fee_payer_asset")!="SOL" or recorded.get("source")!="getFeeForMessage"):
            raise ValueError("recorded signed fee estimate fields inconsistent")
    else:
        raise ValueError("unsupported recorded signed fee estimate status")
    return {"status":"SIGNED_MESSAGE_FEE_ESTIMATE_DIGEST_RECHECKED",
        "signed_message_sha256":expected,"estimated_fee_lamports":value,
        "rpc_fee_value_independently_attested":False,"paid_fee_verified":False,**SAFE}
