import unittest
from unittest.mock import patch
from arb.m5_four_to_six_signed_batch_audit import audit_attempts
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
class SourceSignedMultisizeAuditTests(unittest.TestCase):
    @patch("arb.m5_four_to_six_signed_batch_audit.assess")
    def test_audits_every_distinct_signed_trial(self,assess):
        def audit(f,r):
            ok=r.get("real") is True
            return {"status":"VERIFIED_SIGNED_FOUR_TO_SIX_HOP_ROLLBACK" if ok
                    else "SOURCE_FOUR_TO_SIX_SIGNED_ROLLBACK_UNVERIFIED",
                "failure_reasons":[] if ok else ["missing real receipt"],
                "signed_atomic_simulation_verified":ok,
                "rollback_failure_case_verified":ok,**SAFE}
        assess.side_effect=audit
        receipts={10:{"planned_inputs":[10,9,8,7],"real":False},
                  100:{"planned_inputs":[100,90,80,70],"real":True},
                  1000:{"planned_inputs":[1000,900,800,700],"real":True}}
        r=audit_attempts({},receipts,expected_amounts=(10,100,1000))
        self.assertEqual(r["independently_accepted_amounts_base_units"],[100,1000])
        self.assertEqual(assess.call_count,3)
        self.assertFalse(r["net_profit_verified"])
    @patch("arb.m5_four_to_six_signed_batch_audit.assess")
    def test_actual_signed_start_amount_must_match_requested_size(self,assess):
        assess.return_value={"status":"VERIFIED_SIGNED_FOUR_TO_SIX_HOP_ROLLBACK",
            "failure_reasons":[],"signed_atomic_simulation_verified":True,
            "rollback_failure_case_verified":True,**SAFE}
        r=audit_attempts({}, {100:{"planned_inputs":[200]}},
                         expected_amounts=(100,))
        self.assertEqual(r["independently_accepted_count"],0)
        self.assertIn("signed starting input mismatches size",
                      r["attempts"][0]["audit"]["failure_reasons"])
    def test_unsafe_amount_inventory_rejected(self):
        for sizes in ((),(10,10),(0,10),tuple(range(1,10))):
            with self.assertRaises(ValueError):
                audit_attempts({}, {},expected_amounts=sizes)
if __name__=="__main__":unittest.main()
