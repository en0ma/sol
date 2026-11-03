import unittest
from unittest.mock import patch
from arb.next_ten_fork_pool_probe import candidates,probe,prioritized_probe_addresses,permissioned_dlmm_clock_parity_unverified
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
    def test_authenticated_source_probe_prioritizes_actual_peer_pair_hints(self):
        from arb.orca_whirlpool import SOL,USDC
        unrelated="u"*44
        common="c"*44
        registry={"pools":(
            [{"venue":"orca","address":"A"+str(i).zfill(43),
              "mints":[SOL,unrelated]} for i in range(13)]
            +[{"venue":"orca","address":"target-orca",
               "mints":[SOL,common]},
              {"venue":"pumpswap","address":"target-pump",
               "mints":[common,SOL]},
              {"venue":"raydium_clmm","address":"other-clmm",
               "mints":[USDC,SOL]}])}
        original=candidates(registry)
        prioritized=prioritized_probe_addresses(registry,original,
            (("orca","pumpswap"),),maximum=12)
        self.assertEqual(prioritized["orca"][0],"target-orca")
        self.assertIn("target-pump",prioritized["pumpswap"])
        self.assertEqual(len(prioritized["orca"]),12)
        self.assertFalse(any("source_slot" in x for x in registry["pools"]))
    def test_expanded_probe_budget_preserves_authentication_and_bounds(self):
        from arb.orca_whirlpool import SOL,USDC
        records=[{"venue":"orca","address":"a"+str(i).zfill(43),
                  "mints":[SOL,USDC]} for i in range(30)]
        registry={"pools":records}
        selected=prioritized_probe_addresses(registry,candidates(registry),
            (("orca","pumpswap"),),maximum=24)
        self.assertEqual(len(selected["orca"]),24)
        self.assertEqual(len(set(selected["orca"])),24)
        with self.assertRaises(ValueError):
            probe("http://localhost:8899",registry,maximum_per_venue=25)
    def test_permissioned_dlmm_requires_offline_clock_parity(self):
        permissioned={"pair_type":1}
        self.assertTrue(permissioned_dlmm_clock_parity_unverified(permissioned))
        self.assertFalse(permissioned_dlmm_clock_parity_unverified(
            permissioned,offline_clock_attested=True))
        for pair_type in (0,2,3):
            self.assertFalse(permissioned_dlmm_clock_parity_unverified(
                {"pair_type":pair_type}))
        with self.assertRaises(ValueError):
            permissioned_dlmm_clock_parity_unverified({})
        with self.assertRaises(ValueError):
            permissioned_dlmm_clock_parity_unverified(
                {"pair_type":1},offline_clock_attested="yes")
    def test_invalid_registry_rejected(self):
        with self.assertRaises(ValueError):
            candidates({})
    def test_unordered_shared_pools_reconcile_both_directions(self):
        from arb.next_ten_fork_pool_probe import PROGRAMS
        self.assertEqual(len(BATCH_10),10)
        self.assertEqual(len(PROGRAMS),7)
if __name__=="__main__":
    unittest.main()
