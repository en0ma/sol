import unittest
from unittest.mock import patch
from arb.next_ten_atomic_routes import BATCH_10,NEXT_10,route_batch
from arb.next_ten_fork_pool_probe import probe
from arb.next_ten_atomic_evidence import build
from arb.current_run_atomic_matrix import reconcile

class FollowingTenIntegrationTests(unittest.TestCase):
    def test_inventory_is_eight_new_pairs_and_two_retries(self):
        self.assertEqual(len(NEXT_10),10)
        self.assertEqual(len(set(NEXT_10)-set(BATCH_10)),8)
        self.assertEqual(route_batch("next"),NEXT_10)
    def test_discovery_empty_sources_never_claim_signed_proof(self):
        with patch("arb.next_ten_fork_pool_probe.snapshot",side_effect=ValueError("offline")):
            result=probe("http://127.0.0.1:8899",{"pools":[]},batch=NEXT_10)
        self.assertEqual(len(result["route_candidates"]),10)
        self.assertTrue(all(not x["signed_atomic_simulation_verified"] for x in result["route_candidates"]))
    def test_independent_audit_fails_closed_on_bare_fixtures(self):
        proof=build({NEXT_10[0]:{"status":"SIGNED_ATOMIC_AND_ROLLBACK_VERIFIED"}},batch=NEXT_10)
        self.assertEqual(proof["batch_verified"],0)
    def test_matrix_counts_unique_verified_pairs_only(self):
        from unittest.mock import patch
        from arb.execution_target_matrix import execution_matrix
        with patch("arb.current_run_atomic_matrix.accept",return_value={"verified_ordered_pair_count":0}):
            report=reconcile({},extra_evidence={},next_evidence={})
        self.assertEqual(report["ordered_pair_verified"],0)
        self.assertEqual(report["following_ten_independent_acceptance"]["batch_verified"],0)
    def test_remote_rpc_rejected_without_snapshot(self):
        with patch("arb.next_ten_fork_pool_probe.snapshot") as read:
            with self.assertRaises(ValueError):
                probe("https://api.mainnet-beta.solana.com",{"pools":[]},batch=NEXT_10)
            read.assert_not_called()

if __name__=="__main__":unittest.main()
