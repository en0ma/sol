"""Regress genuine three-hop topology ceilings and bounded bridge suggestions."""
import unittest
from arb.m5_start_mint_expansion import topology,bridge_targets,starting_mint_coverage_pool_subset,SOL,USDC,USDT

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
        self.assertEqual(len(proposal["targets"]),2)
        self.assertEqual(proposal["targets"][0]["mint"],"new")
        self.assertEqual({p["missing_hub"] for p in proposal["targets"]},{USDC,USDT})
        self.assertFalse(proposal["actionable"])
    def test_non_leaf_without_triangle_still_receives_missing_hub_target(self):
        # The old one-neighbor restriction silently excluded this legitimate
        # discovery candidate even though a source-verified second hub pool
        # could close new -> SOL -> USDC -> new.
        rows=self.rows()+[
            {"venue":"pumpswap","address":"extra","mints":["new","other"]}]
        self.assertNotIn("new",topology(rows)["three_hop_start_mints"])
        proposal=bridge_targets(rows,maximum=10)
        self.assertEqual(
            {p["missing_hub"] for p in proposal["targets"] if p["mint"]=="new"},
            {USDC,USDT})
        self.assertFalse(proposal["actionable"])
        self.assertFalse(proposal["broadcast"])
        # Discovery alone cannot count as authenticated execution.
        self.assertTrue(proposal["targets_are_unverified_hints"])

    def test_non_leaf_without_hub_cannot_invent_bridge(self):
        rows=self.rows()+[
            {"venue":"pumpswap","address":"other1","mints":["x","y"]},
            {"venue":"orca","address":"other2","mints":["x","z"]}]
        self.assertFalse(any(p["mint"]=="x" for p in
                             bridge_targets(rows)["targets"]))

    def test_authenticated_bridge_creates_distinct_pool_triangle(self):
        rows=self.rows()+[
            {"venue":"orca","address":"e","mints":["new",USDC]}]
        self.assertEqual(topology(rows)["three_hop_start_mint_count"],4)
        self.assertNotIn("new",[p["mint"] for p in bridge_targets(rows)["targets"]])
    def test_coverage_sampler_prefers_new_start_tokens(self):
        rows=self.rows()+[
            {"venue":"orca","address":"e","mints":["new",USDC]}]
        sample=starting_mint_coverage_pool_subset(rows,
            maximum_per_venue=3,target_start_mints=4)
        self.assertEqual(sample["selected_three_hop_start_mint_count"],4)
        self.assertIn("new",sample["selected_three_hop_start_mints"])
        self.assertFalse(sample["source_authenticated"])
        self.assertFalse(sample["signed_simulation_verified"])
    def test_coverage_sampler_never_invents_missing_pool_topology(self):
        sample=starting_mint_coverage_pool_subset(self.rows(),target_start_mints=40)
        self.assertEqual(sample["selected_three_hop_start_mint_count"],3)
        self.assertEqual(sample["three_hop_mint_topology_ceiling"],3)
    def test_registered_candidate_selection_can_cover_40_under_probe_caps(self):
        import json
        from pathlib import Path
        registry=Path(__file__).resolve().parents[1]/"arb"/"pool_registry.json"
        entries=json.loads(registry.read_text())["pools"]
        sample=starting_mint_coverage_pool_subset(entries,
            maximum_per_venue=24,target_start_mints=40)
        self.assertGreaterEqual(sample["three_hop_mint_topology_ceiling"],40)
        self.assertGreaterEqual(sample["selected_three_hop_start_mint_count"],40)
        self.assertTrue(all(len(addresses)<=24 for addresses in sample["addresses"].values()))
        self.assertFalse(sample["signed_simulation_verified"])
    def test_nonhub_neighbor_can_support_new_authenticated_bridge_hint(self):
        rows=self.rows()+[
            {"venue":"pumpswap","address":"xy","mints":["x","y"]},
            {"venue":"orca","address":"y-usdc","mints":["y",USDC]}]
        self.assertNotIn("x",topology(rows)["three_hop_start_mints"])
        proposals=bridge_targets(rows,maximum=100)
        self.assertTrue(any(p["mint"]=="x" and p["missing_hub"]==USDC
                            and p["connected_hub"]=="y" for p in proposals["targets"]))
        self.assertTrue(proposals["targets_are_unverified_hints"])
        self.assertFalse(proposals["actionable"])

    def test_sampler_keeps_alternative_venue_when_first_six_exhaust_quota(self):
        # An Orca-only slice would fail to cover this triangle with an
        # Orca venue budget of one, despite a valid PumpSwap alternative.
        rows=[
            {"venue":"raydium_cpmm","address":"hub","mints":[SOL,USDC]},
            {"venue":"orca","address":"unique","mints":["new",USDC]},
            {"venue":"pumpswap","address":"alternative","mints":["new",SOL]},
        ]+[
            {"venue":"orca","address":f"duplicate-{i}","mints":["new",SOL]}
            for i in range(8)]
        selected=starting_mint_coverage_pool_subset(
            rows,maximum_per_venue=1,target_start_mints=3)
        self.assertEqual(selected["selected_three_hop_start_mint_count"],3)
        self.assertIn("alternative",selected["addresses"]["pumpswap"])
        self.assertLessEqual(selected["selected_pool_identity_count"],200)
        self.assertFalse(selected["source_authenticated"])
        self.assertFalse(selected["signed_simulation_verified"])

    def test_256_spacing_scanned_without_accepting_unoccupied_pdas(self):
        import base64
        from unittest.mock import patch
        from arb.m5_start_mint_expansion import derive_orca_bridge_addresses
        from arb.orca_whirlpool import PROGRAM,DISCRIMINATOR,SIZE
        raw=bytearray(SIZE)
        raw[:8]=DISCRIMINATOR
        raw[8:40]=bytes(range(32))
        batches=[]
        def source_rpc(rpc,method,params):
            self.assertEqual(method,"getMultipleAccounts")
            addresses=params[0]
            batches.append(addresses)
            if len(batches)==1:
                self.assertEqual(addresses,["source-pool"])
                return {"value":[{"owner":PROGRAM,"data":[
                    base64.b64encode(raw).decode(),"base64"]}]}
            return {"value":[None]*len(addresses)}
        targets=[{"mint":SOL,"missing_hub":USDC}]
        with patch("arb.rpc.call",side_effect=source_rpc):
            result=derive_orca_bridge_addresses(
                "http://127.0.0.1:8899",
                [{"venue":"orca","address":"source-pool","mints":[SOL,USDC]}],
                targets)
        self.assertEqual(result["candidate_pd_as_checked"],9)
        self.assertEqual(result["candidate_tick_spacings"][-1],256)
        self.assertEqual(result["source_verified_pools"],[])
        self.assertEqual(result["source_whirlpool_config_count"],1)
        self.assertEqual(len(set(batches[1])),9)

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
