import unittest
from unittest.mock import patch

from arb.orca_rejection_audit import audit, classify
from arb.orca_whirlpool import PROGRAM

ADDRESS="7qbRF6YsyGuLUVs6Y1q64bdVrfe4ZcUUz1JRdoVNUJnm"

class OrcaRejectionAuditTests(unittest.TestCase):
    @patch("arb.orca_rejection_audit.call")
    def test_missing_pool_is_not_promoted(self, rpc):
        rpc.return_value={"value":None}
        r=classify("rpc",ADDRESS)
        self.assertEqual(r["category"],"POOL_MISSING")
        self.assertFalse(r["verified"])
        self.assertFalse(r["actionable"])

    @patch("arb.orca_rejection_audit.call")
    def test_wrong_program_is_reported_not_accepted(self, rpc):
        rpc.return_value={"value":{"owner":"wrong-program","executable":False}}
        r=classify("rpc",ADDRESS)
        self.assertEqual(r["category"],"POOL_OWNER_MISMATCH")
        self.assertEqual(r["pool_owner"],"wrong-program")
        self.assertFalse(r["verified"])

    @patch("arb.orca_rejection_audit.classify")
    def test_audit_reads_only_rejected_orca_addresses(self, classify):
        classify.return_value={"category":"POOL_MISSING","verified":False}
        report=audit("rpc",{"rejections":[{"venue":"orca","address":ADDRESS},
           {"venue":"pumpswap","address":"other"}]},limit=1)
        self.assertEqual(report["audited"],1)
        self.assertEqual(report["total_rejections"],2)
        self.assertEqual(report["verified_count"],0)
        self.assertFalse(report["mainnet_broadcast"])
        classify.assert_called_once_with("rpc",ADDRESS)

    def test_bounded_audit(self):
        with self.assertRaises(ValueError):
            audit("rpc",{"rejections":[]},limit=201)
