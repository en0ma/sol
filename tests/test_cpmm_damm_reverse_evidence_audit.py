import unittest
from arb.cpmm_damm_reverse_evidence_audit import accept_reverse

class ReverseEvidenceSafetyTests(unittest.TestCase):
    def test_unverified_fixtures_cannot_count(self):
        self.assertEqual(accept_reverse({})["verified_ordered_pair_count"],0)
    def test_success_flag_without_balances_cannot_count(self):
        x={"status":"SIGNED_REVERSE_ATOMIC_AND_ROLLBACK_VERIFIED",
           "signed_atomic_simulation_verified":True,
           "rollback_failure_case_verified":True,
           "intermediate_intra_transaction_consumption_verified":True,
           "instruction_order_verified":True,
           "failed_at_second_instruction_after_successful_first":True,
           "actionable":False,"live_execution_approved":False,"broadcast":False}
        self.assertEqual(accept_reverse(x)["verified_ordered_pair_count"],0)
    def test_forward_order_cannot_count_reverse(self):
        from arb.damm_cpmm_atomic_offline import DAMM,CPMM
        x={"first_venue":"meteora_damm_v2","second_venue":"raydium_cpmm",
           "top_level_venue_events":[[DAMM,"invoke"],[DAMM,"success"],
                                     [CPMM,"invoke"],[CPMM,"success"]]}
        self.assertEqual(accept_reverse(x)["verified_ordered_pair_count"],0)

if __name__=="__main__":
    unittest.main()
