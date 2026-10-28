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
    @patch("arb.m5_four_to_six_signed_batch_audit.assess")
    def test_source_fee_estimated_net_only_when_starting_mint_is_wsol(self,assess):
        from arb.m5_signed_start_mint_economics import WSOL
        def audit(f,r):
            return {"status":"VERIFIED_SIGNED_FOUR_TO_SIX_HOP_ROLLBACK",
                "failure_reasons":[],"hops":4,
                "source_manifest_sha256":"authenticated",
                "signed_atomic_simulation_verified":True,
                "rollback_failure_case_verified":True,**SAFE}
        assess.side_effect=audit
        fee={"status":"SIGNED_MESSAGE_FEE_ESTIMATE_ONLY",
             "fee_payer_asset":"SOL","estimated_fee_lamports":5000,**SAFE}
        receipts={
            100000:{"planned_inputs":[100000,90000,80000,70000],
                 "state_accounts_observed_slot":88,
                 "positive_post_balances_base_units":[0,0,0,0,120000],
                 "signed_message_fee_estimate":fee,
                 "signed_atomic_simulation_verified":True,**SAFE},
            200000:{"planned_inputs":[200000,190000,180000,170000],
                 "state_accounts_observed_slot":88,
                 "positive_post_balances_base_units":[0,0,0,0,208000],
                 "signed_message_fee_estimate":fee,
                 "signed_atomic_simulation_verified":True,**SAFE}}
        wsol={"route_mints":[WSOL,"B","C","D",WSOL],
              "state_accounts_observed_slot":88}
        result=audit_attempts(wsol,receipts,expected_amounts=(100000,200000))
        self.assertEqual(result["estimated_net_start_mint_comparable_count"],2)
        self.assertEqual(result["estimated_net_research_only_ranking"][0]
                         ["estimated_net_start_mint_delta_base_units"],15000)
        self.assertFalse(result["net_profit_verified"])
        assert not result["ranked_net_profitable_candidates"]
        ray={"route_mints":["RAY","B","C","D","RAY"],
             "state_accounts_observed_slot":88}
        ray_result=audit_attempts(ray,receipts,expected_amounts=(100000,200000))
        self.assertEqual(ray_result["estimated_net_start_mint_comparable_count"],0)
        self.assertEqual(ray_result["signed_gross_observation_count"],2)
    def test_unsafe_amount_inventory_rejected(self):
        for sizes in ((),(10,10),(0,10),tuple(range(1,10))):
            with self.assertRaises(ValueError):
                audit_attempts({}, {},expected_amounts=sizes)
if __name__=="__main__":unittest.main()
