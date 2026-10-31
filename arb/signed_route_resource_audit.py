"""Independent signed-wire and offline resource diagnostic; never fee acceptance.

A signature-verified packet and an RPC-reported compute count do not prove
network fees paid, the authenticity of an upstream fork, or profitability.
No transaction broadcast or writable RPC calls occur here.
"""
import hashlib

MAX_CU=1_400_000
MAX_PACKET_BYTES=1232
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}


def inspect_signed_offline_resources(wire, simulation, *, expected_wire_sha256):
    """Verify actual Ed25519 signatures and bounded compute on supplied bytes.

    The independent caller must bind the wire to source-state provenance and
    verify CPI/SPL poststate and rollback elsewhere. A green simulation alone
    is not signed execution acceptance or an observed network fee.
    """
    from solders.transaction import VersionedTransaction
    if (not isinstance(wire,bytes) or not 0<len(wire)<=MAX_PACKET_BYTES
            or type(expected_wire_sha256)is not str
            or len(expected_wire_sha256)!=64
            or any(ch not in "0123456789abcdef" for ch in expected_wire_sha256)):
        raise ValueError("bounded signed wire and packet digest required")
    digest=hashlib.sha256(wire).hexdigest()
    if digest!=expected_wire_sha256:
        raise ValueError("signed packet digest mismatch")
    try:
        tx=VersionedTransaction.from_bytes(wire)
        tx.verify_and_hash_message()
    except Exception as exc:
        raise ValueError("signed wire Ed25519 verification failed") from exc
    if not tx.signatures:
        raise ValueError("unsigned packet rejected")
    if not isinstance(simulation,dict) or simulation.get("err") is not None:
        raise ValueError("successful offline simulation result required")
    cu=simulation.get("unitsConsumed")
    if type(cu)is not int or not 0<cu<=MAX_CU:
        raise ValueError("missing or out-of-bounds actual simulated compute")
    # The signature identifies the signed packet, NOT an on-chain confirmation.
    signature=str(tx.signatures[0])
    return {"status":"SIGNED_WIRE_AND_OFFLINE_COMPUTE_DIAGNOSTIC_ONLY",
            "signed_packet_sha256":digest,"first_signature":signature,
            "signatures_count":len(tx.signatures),"packet_size_bytes":len(wire),
            "observed_simulation_compute_units":cu,
            "independent_fee_paid_verified":False,
            "fee_lamports":None,
            "signed_cpi_per_leg_verified":False,
            "signed_spl_poststate_verified":False,
            "rollback_control_verified":False,**SAFE}


def quote_signed_message_fee_offline(rpc, wire, simulation, *, expected_wire_sha256):
    """Read an RPC fee quote bound to the exact verified signed message.

    getFeeForMessage is a *quote*, not an actual paid transaction fee.
    Never insert this return value into verified net-profitability fields.
    No send, simulateTransaction or write RPC calls are made here.
    """
    import base64
    from solders.transaction import VersionedTransaction
    from arb.pumpswap_local_simulation import local_rpc_only
    from arb.rpc import call

    local_rpc_only(rpc)
    report=inspect_signed_offline_resources(
        wire,simulation,expected_wire_sha256=expected_wire_sha256)
    tx=VersionedTransaction.from_bytes(wire)
    message_bytes=bytes(tx.message)
    response=call(rpc,"getFeeForMessage",[
        base64.b64encode(message_bytes).decode("ascii"),
        {"commitment":"processed"}])
    if (not isinstance(response,dict)
            or type(response.get("value")) is not int
            or not 0<=response["value"]<2**64
            or not isinstance(response.get("context"),dict)
            or type(response["context"].get("slot")) is not int
            or response["context"]["slot"]<0):
        raise ValueError("authenticated-looking but invalid fee quote response")
    return {**report,
            "status":"SIGNED_MESSAGE_FEE_QUOTE_NOT_PAID_FEE",
            "signed_message_sha256":hashlib.sha256(message_bytes).hexdigest(),
            "quoted_fee_lamports":response["value"],
            "quote_context_slot":response["context"]["slot"],
            "fee_lamports":None,
            "independent_fee_paid_verified":False}


def inspect_local_recorded_transaction_fee(rpc, wire, simulation, *, expected_wire_sha256):
    """Match a local-fork recorded transaction to the exact signed packet.

    This only reports local ledger metadata, never mainnet settlement or
    independently authenticated economic spend. A missing transaction fails.
    """
    import base64
    from arb.pumpswap_local_simulation import local_rpc_only
    from arb.rpc import call
    local_rpc_only(rpc)
    report=inspect_signed_offline_resources(
        wire,simulation,expected_wire_sha256=expected_wire_sha256)
    response=call(rpc,"getTransaction",[
        report["first_signature"],
        {"encoding":"base64","commitment":"confirmed",
         "maxSupportedTransactionVersion":0}])
    if not isinstance(response,dict):
        raise ValueError("local transaction receipt absent")
    transaction=response.get("transaction")
    meta=response.get("meta")
    if (not isinstance(transaction,list) or len(transaction)!=2
            or transaction[1]!="base64" or not isinstance(transaction[0],str)):
        raise ValueError("local recorded wire unavailable")
    try:
        recorded=base64.b64decode(transaction[0],validate=True)
    except (ValueError,base64.binascii.Error) as exc:
        raise ValueError("invalid local transaction encoding") from exc
    if recorded!=wire:
        raise ValueError("local transaction signed bytes mismatch")
    if (type(response.get("slot")) is not int or response["slot"]<0
            or not isinstance(meta,dict) or meta.get("err") is not None
            or type(meta.get("fee")) is not int or not 0<=meta["fee"]<2**64
            or type(meta.get("computeUnitsConsumed")) is not int
            or not 0<meta["computeUnitsConsumed"]<=MAX_CU):
        raise ValueError("invalid local recorded fee or execution metadata")
    return {**report,
            "status":"LOCAL_RECORDED_TRANSACTION_FEE_DIAGNOSTIC_ONLY",
            "local_recorded_slot":response["slot"],
            "local_recorded_fee_lamports":meta["fee"],
            "local_recorded_compute_units":meta["computeUnitsConsumed"],
            "independent_fee_paid_verified":False,
            "fee_lamports":None}
