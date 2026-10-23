import unittest
from arb.execution_target_matrix import execution_matrix, TARGET_VENUES

class ExecutionTargetMatrixTests(unittest.TestCase):
    def test_all_eight_venues_and_all_56_orders_included(self):
        report=execution_matrix()
        self.assertEqual(report["venue_target"],8)
        self.assertEqual(len(report["venues"]),8)
        self.assertEqual(report["decoder_implemented"],6)
        self.assertEqual(report["builder_implemented"],4)
        self.assertEqual(report["unordered_pair_target"],28)
        self.assertEqual(report["ordered_pair_target"],56)
        self.assertEqual(len({(p["first_venue"],p["second_venue"])
                              for p in report["ordered_pairs"]}),56)
        self.assertEqual({r["venue"] for r in report["venues"]},set(TARGET_VENUES))

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

    def test_missing_venue_builders_are_explicit(self):
        report=execution_matrix()
        venues={v["venue"]:v for v in report["venues"]}
        for name in ("meteora_damm_v2","pumpswap"):
            self.assertTrue(venues[name]["pool_decoder_implemented"])
            self.assertFalse(venues[name]["signed_swap_builder_implemented"])
        for name in ("raydium_amm_v4","orca_token_swap_v1"):
            self.assertFalse(venues[name]["pool_decoder_implemented"])
            self.assertFalse(venues[name]["signed_swap_builder_implemented"])
