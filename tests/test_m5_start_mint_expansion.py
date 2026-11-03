"""Regress genuine three-hop topology ceilings and bounded bridge suggestions."""
import unittest
from arb.m5_start_mint_expansion import topology,bridge_targets,SOL,USDC,USDT

class StartMintExpansionTests(unittest.TestCase):
    def rows(self):
        return [
            {"venue":"orca","address":"a","mints":["new",SOL]},
            {"venue":"raydium_cpmm","address":"b","mints":[SOL,USDC]},
            {"venue":"meteora_damm_v2","address":"c","mints":[USDC,USDT]},
            {"venue":"meteora_dlmm","address":"d","mints":[USDT,SOL]},
        ]
    def test_three_hop_ceiling_excludes_leaf_with_one_hub(self):
        t=topology(self.rows())
        self.assertEqual(t["three_hop_start_mint_count"],3)
        self.assertNotIn("new",t["three_hop_start_mints"])
        proposal=bridge_targets(self.rows(),maximum=4)
        self.assertEqual(len(proposal["targets"]),1)
        self.assertEqual(proposal["targets"][0]["mint"],"new")
        self.assertIn(proposal["targets"][0]["missing_hub"],(USDC,USDT))
        self.assertFalse(proposal["actionable"])
    def test_authenticated_bridge_creates_distinct_pool_triangle(self):
        rows=self.rows()+[
            {"venue":"orca","address":"e","mints":["new",USDC]}]
        self.assertEqual(topology(rows)["three_hop_start_mint_count"],4)
        self.assertNotIn("new",[p["mint"] for p in bridge_targets(rows)["targets"]])
    def test_duplicate_pool_and_invalid_budget_rejected(self):
        with self.assertRaisesRegex(ValueError,"duplicate pool"):
            topology(self.rows()+[self.rows()[0]])
        with self.assertRaises(ValueError):
            bridge_targets(self.rows(),maximum=0)
    def test_duplicated_pair_does_not_invent_new_start(self):
        rows=self.rows()+[
            {"venue":"meteora_dlmm","address":"e","mints":["new",SOL]}]
        self.assertNotIn("new",topology(rows)["three_hop_start_mints"])

if __name__=="__main__":unittest.main()
