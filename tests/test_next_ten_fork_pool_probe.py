import unittest
from unittest.mock import patch
from arb.next_ten_fork_pool_probe import candidates,probe
from arb.next_ten_atomic_routes import BATCH_10
class ForkCandidateTests(unittest.TestCase):
    def test_untrusted_mainnet_rpc_blocked_without_reads(self):
        with patch("arb.next_ten_fork_pool_probe.call") as rpc:
            with self.assertRaises(ValueError):
                probe("https://api.mainnet-beta.solana.com",{"pools":[]})
            rpc.assert_not_called()
    def test_missing_pools_cannot_claim_execution(self):
        with patch("arb.next_ten_fork_pool_probe.snapshot",
                   side_effect=ValueError("missing")):
            result=probe("http://localhost:8899",{"pools":[]})
        self.assertEqual(len(result["route_candidates"]),10)
        self.assertTrue(all(not r["signed_atomic_simulation_verified"]
                            for r in result["route_candidates"]))
        self.assertFalse(result["broadcast"])
    def test_invalid_registry_rejected(self):
        with self.assertRaises(ValueError):
            candidates({})
    def test_unordered_shared_pools_reconcile_both_directions(self):
        from arb.next_ten_fork_pool_probe import PROGRAMS
        self.assertEqual(len(BATCH_10),10)
        self.assertEqual(len(PROGRAMS),7)
if __name__=="__main__":
    unittest.main()
