import unittest
from arb.next_ten_atomic_routes import BATCH_10
from arb.next_ten_atomic_evidence import assess, build

class ExpansionSafetyTests(unittest.TestCase):
    def test_all_ten_unique_ordered_pairs_are_eligible(self):
        self.assertEqual(len(BATCH_10),10)
        self.assertEqual(len(set(BATCH_10)),10)
    def test_absent_runtime_evidence_gives_zero(self):
        report=build({})
        self.assertEqual(report["batch_verified"],0)
        self.assertEqual(len(report["routes"]),10)
        self.assertFalse(report["broadcast"])
    def test_success_claim_without_runtime_proof_rejected(self):
        a,b=BATCH_10[0]
        proof={"first_venue":a,"second_venue":b,
               "signed_atomic_simulation_verified":True,
               "intermediate_intra_transaction_consumption_verified":True,
               "rollback_failure_case_verified":True,
               "instruction_order_verified":True,
               "actionable":False,"live_execution_approved":False,"broadcast":False}
        self.assertEqual(assess((a,b),proof)["status"],"UNVERIFIED")
    def test_reverse_does_not_count_for_opposite_order(self):
        first,second=BATCH_10[0]
        proof={"first_venue":second,"second_venue":first}
        self.assertEqual(assess((first,second),proof)["status"],"UNVERIFIED")
    def test_unrecognized_route_rejected(self):
        with self.assertRaises(ValueError):
            build({("orca","orca"):{"signed_atomic_simulation_verified":True}})
if __name__=="__main__":
    unittest.main()
