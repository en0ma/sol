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
        for size,receipt in receipts.items():
            receipt["signed_transaction_sha256"]=f"{size:064x}"
            receipt["negative_signed_transaction_sha256"]=f"{size+1:064x}"
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
        for size,receipt in receipts.items():
            receipt["signed_transaction_sha256"]=f"{size:064x}"
            receipt["negative_signed_transaction_sha256"]=f"{size+1:064x}"
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

class SignedPacketReplayAcrossSizesTests(unittest.TestCase):
    @patch("arb.m5_four_to_six_signed_batch_audit.assess")
    def test_second_claim_reusing_signed_packet_is_not_accepted(self,assess):
        assess.return_value={
            "status":"VERIFIED_SIGNED_FOUR_TO_SIX_HOP_ROLLBACK",
            "hops":4,"failure_reasons":[],
            "signed_atomic_simulation_verified":True,
            "rollback_failure_case_verified":True,**SAFE}
        receipts={}
        for amount in (100,200):
            receipts[amount]={
                "planned_inputs":[amount,90,80,70],
                "signed_transaction_sha256":"a"*64,
                "negative_signed_transaction_sha256":"b"*64}
        report=audit_attempts({},receipts,expected_amounts=(100,200))
        self.assertEqual(report["independently_accepted_count"],1)
        self.assertIn("replay",report["attempts"][1]["audit"]["failure_reasons"][0])

class VenueNativeAccuracyDiagnosticsTests(unittest.TestCase):
    @patch("arb.m5_four_to_six_signed_batch_audit.assess")
    @patch("arb.m5_source_signed_prefix_quote_parity.compare")
    def test_independent_native_errors_aggregate_by_venue(self,compare,assess):
        assess.return_value={
            "status":"VERIFIED_SIGNED_FOUR_TO_SIX_HOP_ROLLBACK","hops":4,
            "failure_reasons":[],"source_manifest_sha256":"a",
            "signed_atomic_simulation_verified":True,
            "rollback_failure_case_verified":True,**SAFE}
        compare.return_value={
            "status":"SOURCE_NATIVE_TO_SIGNED_ALL_LEGS_COMPARISON",
            "atomic_execution_independently_accepted":True,
            "source_slot":50,"compared_signed_legs":4,
            "atomic_terminal_observation_used":True,
            "numeric_comparison_count":2,
            "comparisons":[
                {"venue":"orca","modeled_minus_signed_base_units":-4},
                {"venue":"raydium_clmm","modeled_minus_signed_base_units":12},
                {"venue":"raydium_clmm","modeled_minus_signed_base_units":None},
                {"venue":"meteora_dlmm","modeled_minus_signed_base_units":None}],**SAFE}
        fee={"status":"SIGNED_MESSAGE_FEE_ESTIMATE_ONLY",
             "fee_payer_asset":"SOL","estimated_fee_lamports":5,**SAFE}
        from arb.m5_signed_start_mint_economics import WSOL
        fixture={"state_accounts_observed_slot":50,
                 "route_mints":[WSOL,"B","C","D",WSOL],**SAFE}
        receipt={"planned_inputs":[100,70,60,50],
                 "signed_transaction_sha256":"a"*64,
                 "negative_signed_transaction_sha256":"b"*64,
                 "state_accounts_observed_slot":50,
                 "positive_post_balances_base_units":[0,0,0,0,95],
                 "signed_message_fee_estimate":fee,
                 "signed_atomic_simulation_verified":True,**SAFE}
        report=audit_attempts(fixture,{100:receipt},
            expected_amounts=(100,),observed_unix=123)
        venues={r["venue"]:r for r in report[
            "per_venue_signed_native_error_diagnostics"]}
        self.assertEqual(venues["raydium_clmm"]["absolute_source_model_error_sum_base_units"],12)
        self.assertEqual(venues["raydium_clmm"]["signed_native_unresolved_comparisons"],1)
        self.assertEqual(report["signed_start_mint_break_even_cost_budgets"][0][
            "maximum_start_mint_cost_for_nonnegative_net_base_units"],0)
        self.assertFalse(report["net_profit_verified"])
