import unittest

from arb.damm_v2_execution_evidence_audit import audit
from arb.meteora_damm_v2 import PROGRAM

def fixture():
    return {
        "status": "ISOLATED_DAMM_V2_SIGNED_SWAP_VERIFIED",
        "venue": "meteora_damm_v2", "program": PROGRAM,
        "signed_standalone_simulation_verified": True,
        "pool_reauthenticated": True,
        "positive_and_negative_controls_verified": True,
        "negative_slippage_failure_observed": True, "local_only": True,
        "actionable": False, "live_execution_approved": False, "broadcast": False,
        "pool": "pool", "input_mint": "mint1", "output_mint": "mint2",
        "input_account": "account1", "output_account": "account2",
        "transaction_signature": "sig-positive", "negative_signature": "sig-negative",
        "authenticated_slot": 1653, "fixture_snapshot_slot": 460638760,
        "user_snapshot_slot": 1647,
        "requested_input_base_units": 1000, "spent_input_base_units": 1000,
        "received_output_base_units": 101, "requested_min_output_base_units": 1,
        "min_output_base_units": 1,
        "negative_error": "{'InstructionError': [0, {'Custom': 6002}]}",
        "negative_logs": [
            "Program " + PROGRAM + " invoke [1]",
            "Program log: AnchorError: Error Code: ExceededSlippage. Error Number: 6002.",
        ]
    }

class AuditTests(unittest.TestCase):
    def test_complete_fork_evidence_accepted(self):
        result = audit(fixture())
        self.assertEqual(result["status"], "ACCEPTED")
        self.assertEqual(result["spent_input_base_units"], 1000)
        self.assertEqual(result["received_output_base_units"], 101)
        self.assertFalse(result["broadcast"])

    def test_missing_simulation_proof_fails_closed(self):
        record = fixture()
        record["signed_standalone_simulation_verified"] = False
        self.assertFalse(audit(record)["signed_standalone_execution_accepted"])

    def test_wrong_negative_error_fails_closed(self):
        record = fixture()
        record["negative_error"] = "BlockhashNotFound"
        record["negative_logs"] = []
        self.assertFalse(audit(record)["signed_standalone_execution_accepted"])

    def test_insufficient_output_fails_closed(self):
        record = fixture()
        record["requested_min_output_base_units"] = 102
        self.assertFalse(audit(record)["signed_standalone_execution_accepted"])

    def test_unsafe_flags_fail_closed(self):
        record = fixture()
        record["broadcast"] = True
        self.assertFalse(audit(record)["signed_standalone_execution_accepted"])

if __name__ == "__main__":
    unittest.main()
