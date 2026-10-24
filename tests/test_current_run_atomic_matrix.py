import unittest
from unittest.mock import patch
from arb.current_run_atomic_matrix import reconcile
from tests.test_damm_cpmm_atomic_evidence_audit import valid

class CurrentRunMatrixTests(unittest.TestCase):
    def test_no_evidence_does_not_mark_any_pair(self):
        report=reconcile({})
        self.assertEqual(report["ordered_pair_verified"],0)
        self.assertEqual(len(report["ordered_pairs"]),42)
        self.assertTrue(all(not row["current_run_atomic_execution_verified"]
                            for row in report["ordered_pairs"]))
    def test_accepted_evidence_marks_exactly_one_direction(self):
        report=reconcile(valid())
        self.assertEqual(report["ordered_pair_verified"],1)
        verified=[row for row in report["ordered_pairs"]
                  if row["current_run_atomic_execution_verified"]]
        self.assertEqual([(x["first_venue"],x["second_venue"]) for x in verified],
                         [("meteora_damm_v2","raydium_cpmm")])
        self.assertTrue(verified[0]["rollback_verified"])
        self.assertFalse(report["broadcast"])
    def test_negative_failed_control_does_not_get_credit(self):
        proof=valid()
        proof["rollback_failure_case_verified"]=False
        self.assertEqual(reconcile(proof)["ordered_pair_verified"],0)

if __name__=="__main__":
    unittest.main()
