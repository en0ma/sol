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
    msg=bytes(transaction.message)
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
