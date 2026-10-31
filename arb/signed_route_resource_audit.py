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
