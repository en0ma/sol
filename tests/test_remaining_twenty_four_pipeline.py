import unittest
from unittest.mock import patch
from arb.next_ten_atomic_routes import REMAINING_42,ALL_42
from arb.next_ten_atomic_evidence import build
from arb.current_run_atomic_matrix import reconcile
from arb.next_ten_fork_pool_probe import probe,PROGRAMS

class RemainingRoutePipelineTests(unittest.TestCase):
    def test_remaining_inventory_contains_every_missing_ordered_pair(self):
        self.assertEqual(len(REMAINING_42),24)
        self.assertEqual(len(ALL_42),42)
        self.assertTrue(any("raydium_clmm" in r for r in REMAINING_42))
        self.assertTrue(any("raydium_amm_v4" in r for r in REMAINING_42))
    def test_remaining_probe_discovers_all_target_venue_identities(self):
        with patch("arb.next_ten_fork_pool_probe.snapshot",side_effect=ValueError("unavailable")):
            report=probe("http://localhost:8899",{"pools":[]},batch=REMAINING_42)
        self.assertEqual(len(report["route_candidates"]),24)
        self.assertEqual(len(PROGRAMS),7)
    def test_unproven_remaining_routes_never_count(self):
        report=build({},batch=REMAINING_42)
        self.assertEqual(report["batch_verified"],0)
        self.assertEqual(report["batch_unverified"],24)
    def test_matrix_reconciles_remaining_batch_without_fabricating_success(self):
        with patch("arb.current_run_atomic_matrix.accept",return_value={"verified_ordered_pair_count":0}):
            report=reconcile({},remaining_evidence={REMAINING_42[0]:{"status":"SIGNED_ATOMIC_AND_ROLLBACK_VERIFIED"}})
        self.assertEqual(report["ordered_pair_verified"],0)
        self.assertEqual(report["remaining_twenty_four_independent_acceptance"]["batch_verified"],0)
if __name__=="__main__":unittest.main()
