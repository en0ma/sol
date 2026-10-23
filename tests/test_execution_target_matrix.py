import unittest
from arb.execution_target_matrix import execution_matrix, TARGET_VENUES

class ExecutionTargetMatrixTests(unittest.TestCase):
    def test_all_seven_active_venues_and_all_42_orders_included(self):
        report=execution_matrix()
        self.assertEqual(report["venue_target"],7)
        self.assertEqual(len(report["venues"]),7)
        self.assertEqual(report["decoder_implemented"],7)
        self.assertEqual(report["builder_implemented"],7)
        self.assertEqual(report["unordered_pair_target"],21)
        self.assertEqual(report["ordered_pair_target"],42)
        self.assertEqual(len({(p["first_venue"],p["second_venue"])
                              for p in report["ordered_pairs"]}),42)
        self.assertEqual({r["venue"] for r in report["venues"]},set(TARGET_VENUES))
        self.assertEqual(report["archived_optional_venues"],["orca_token_swap_v1"])
        self.assertNotIn("orca_token_swap_v1",TARGET_VENUES)

    def test_builder_not_equivalent_to_current_execution(self):
        report=execution_matrix()
        for venue in report["venues"]:
            self.assertFalse(venue["current_run_standalone_execution_verified"])
            self.assertFalse(venue["standalone_execution_ready_this_run"])
        for pair in report["ordered_pairs"]:
            self.assertFalse(pair["this_execution_order_verified"])
            self.assertFalse(pair["current_run_atomic_execution_verified"])
            self.assertFalse(pair["intermediate_token_balance_verified"])
            self.assertFalse(pair["rollback_verified"])
        self.assertFalse(report["actionable"])
        self.assertFalse(report["live_execution_approved"])
        self.assertFalse(report["broadcast"])

    def test_historical_unordered_evidence_not_promoted_to_ordered(self):
        report=execution_matrix()
        pair=next(p for p in report["ordered_pairs"]
                  if p["first_venue"]=="orca" and p["second_venue"]=="raydium_cpmm")
        self.assertIsNotNone(pair["unordered_historical_pair_evidence"])
        self.assertFalse(pair["this_execution_order_verified"])

    def test_all_seven_active_modules_present_but_no_new_execution_claim(self):
        report=execution_matrix()
        venues={v["venue"]:v for v in report["venues"]}
        for name in TARGET_VENUES:
            self.assertTrue(venues[name]["pool_decoder_implemented"],name)
            self.assertTrue(venues[name]["signed_swap_builder_implemented"],name)
            self.assertFalse(venues[name]["current_run_standalone_execution_verified"])
        self.assertEqual(report["historical_standalone_evidence"],4)
        self.assertEqual(report["current_run_standalone_verified"],0)
        self.assertEqual(report["ordered_pair_verified"],0)
        self.assertTrue(all(p["both_decoders_implemented"] and
                            p["both_builders_implemented"] for p in report["ordered_pairs"]))
