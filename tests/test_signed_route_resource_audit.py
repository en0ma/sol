"""Signed offline packet/resource diagnostics must never certify network fees."""
import hashlib
import unittest
from solders.hash import Hash
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.instruction import Instruction
from solders.transaction import Transaction
from arb.signed_route_resource_audit import inspect_signed_offline_resources


def signed_wire():
    signer=Keypair()
    ix=Instruction(Pubkey.new_unique(),bytes([1]),[])
    tx=Transaction.new_signed_with_payer([ix],signer.pubkey(),[signer],Hash.default())
    tx.verify()
    wire=bytes(tx)
    return wire,hashlib.sha256(wire).hexdigest()


class SignedResourceAuditTests(unittest.TestCase):
    def test_valid_signed_wire_is_not_fee_acceptance(self):
        wire,digest=signed_wire()
        out=inspect_signed_offline_resources(
            wire,{"err":None,"unitsConsumed":100_000},expected_wire_sha256=digest)
        self.assertEqual(out["signed_packet_sha256"],digest)
        self.assertEqual(out["observed_simulation_compute_units"],100_000)
        self.assertEqual(out["signatures_count"],1)
        self.assertIsNone(out["fee_lamports"])
        for field in ("independent_fee_paid_verified","actionable",
                      "live_execution_approved","broadcast",
                      "signed_cpi_per_leg_verified","rollback_control_verified"):
            self.assertFalse(out[field])
    def test_tamper_digest_and_invalid_signature(self):
        wire,digest=signed_wire()
        with self.assertRaisesRegex(ValueError,"digest mismatch"):
            inspect_signed_offline_resources(wire,{"err":None,"unitsConsumed":100},expected_wire_sha256="0"*64)
        altered=bytearray(wire)
        altered[10]^=1
        altered=bytes(altered)
        with self.assertRaisesRegex(ValueError,"Ed25519"):
            inspect_signed_offline_resources(
                altered,{"err":None,"unitsConsumed":100},
                expected_wire_sha256=hashlib.sha256(altered).hexdigest())
    def test_bad_compute_and_simulated_failure_blocked(self):
        wire,digest=signed_wire()
        for result in ({"unitsConsumed":0},{"unitsConsumed":True},
                       {"unitsConsumed":1_400_001},{"unitsConsumed":1.5},
                       {"err":{"InstructionError":[0,"Custom"]},"unitsConsumed":100},
                       {}):
            with self.subTest(result=result):
                with self.assertRaises(ValueError):
                    inspect_signed_offline_resources(wire,result,expected_wire_sha256=digest)
    def test_wire_size_and_digest_type_blocked(self):
        wire,digest=signed_wire()
        for data,sha in ((wire+b"x"*1232,digest),(wire,"f"*63),
                         (wire,None),(wire.hex(),digest)):
            with self.assertRaises(ValueError):
                inspect_signed_offline_resources(data,{"unitsConsumed":1},expected_wire_sha256=sha)


if __name__=="__main__":
    unittest.main()
