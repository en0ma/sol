import unittest
from arb.registry_pair_reconciliation import reconcile
from arb.registry_multihop_cycles import discover_cycles
from arb.orca_whirlpool import SOL, USDC

class RegistryPairReconciliationTests(unittest.TestCase):
    def test_authenticated_mints_connect_real_pools_in_graph(self):
        hints=[{"venue":"orca","address":"a"*40},
               {"venue":"raydium_clmm","address":"b"*40}]
        evidence=[{"venue":h["venue"],"address":h["address"],
                   "mints":[SOL,USDC],"slot":123,"verified":True,
                   "vault_base_units":[100,200]} for h in hints]
        r=reconcile(hints,evidence,target=1)
        self.assertEqual(r["admitted"],2)
        self.assertEqual(len(r["cross_venue_shared_pairs"]),1)
        self.assertGreater(r["cross_venue_closed_cycle_count"],0)
        self.assertEqual(r["venue_coverage"]["orca"]["closed_cross_venue_cycle_pools"],1)
        self.assertEqual(r["venue_coverage"]["orca"]["cross_venue_shared_pair"],1)
        self.assertFalse(r["seven_venue_target_met"])
        self.assertEqual(len(r["venue_coverage"]),7)
        self.assertEqual(r["venue_coverage"]["raydium_amm_v4"]["authenticated"],0)
        cycles=discover_cycles(r["graph_pools"],min_hops=2,max_hops=2)
        self.assertGreater(cycles["cycle_count"],0)
        self.assertTrue(all(x["broadcast"] is False for x in cycles["cycles"]))
    def test_missing_mints_remain_unverified(self):
        hints=[{"venue":"orca","address":"a"*40}]
        r=reconcile(hints,[],target=20)
        self.assertEqual(r["admitted"],0)
        self.assertEqual(r["venue_coverage"]["orca"]["missing_to_target"],20)
        self.assertFalse(r["seven_venue_target_met"])
    def test_forged_identity_and_mismatched_pair_are_rejected(self):
        hints=[{"venue":"orca","address":"a"*40,"mints":[SOL,USDC]}]
        good={"venue":"orca","address":"a"*40,"mints":[SOL,USDC],
              "verified":True,"slot":123,"vault_base_units":[1,1]}
        for forged in (
            {**good,"mints":[USDC,"x"*44]},
            {**good,"verified":False},
            {**good,"vault_base_units":[0,1]},
            {**good,"slot":True},
            {**good,"address":"b"*40},
        ):
            with self.assertRaises(ValueError):
                reconcile(hints,[forged])
    def test_isolated_liquidity_cannot_satisfy_twenty_connected_pool_target(self):
        hints=[{"venue":"orca","address":str(i).zfill(44)} for i in range(20)]
        evidence=[{"venue":"orca","address":h["address"],"mints":[SOL,USDC],
                   "verified":True,"slot":123,"vault_base_units":[1,1]} for h in hints]
        result=reconcile(hints,evidence,target=20)
        self.assertEqual(result["venue_coverage"]["orca"]["authenticated"],20)
        self.assertEqual(result["venue_coverage"]["orca"]["cross_venue_mint_connected"],0)
        self.assertEqual(result["venue_coverage"]["orca"]["missing_to_target"],20)
        self.assertEqual(result["venue_coverage"]["orca"]["closed_cross_venue_cycle_pools"],0)
        self.assertFalse(result["venue_coverage"]["orca"]["target_met"])
    def test_shared_hub_only_does_not_form_closed_cross_venue_connector(self):
        token="x"*44
        hints=[{"venue":"orca","address":"a"*44},
               {"venue":"raydium_clmm","address":"b"*44}]
        evidence=[{"venue":"orca","address":"a"*44,"mints":[SOL,token],
                   "verified":True,"slot":123,"vault_base_units":[1,1]},
                  {"venue":"raydium_clmm","address":"b"*44,"mints":[SOL,USDC],
                   "verified":True,"slot":123,"vault_base_units":[1,1]}]
        report=reconcile(hints,evidence,target=1)
        self.assertEqual(report["venue_coverage"]["orca"]["cross_venue_mint_connected"],0)
        self.assertEqual(report["venue_coverage"]["raydium_clmm"]["cross_venue_mint_connected"],0)
        self.assertFalse(report["seven_venue_target_met"])
    def test_usdt_anchor_cycles_with_verified_distinct_venue_pools(self):
        from arb.onchain_pool_discovery import USDT
        hints=[{"venue":"orca","address":"a"*44},
               {"venue":"raydium_clmm","address":"b"*44}]
        evidence=[{"venue":h["venue"],"address":h["address"],
                   "mints":[USDT,SOL],"verified":True,"slot":123,
                   "vault_base_units":[100,100]} for h in hints]
        report=reconcile(hints,evidence,target=1)
        cycles=discover_cycles(report["graph_pools"],min_hops=2,max_hops=2,starts=(USDT,))
        self.assertGreater(cycles["cycle_count"],0)
        self.assertTrue(all(c["tokens"][0]==USDT for c in cycles["cycles"]))
    def test_unknown_symbols_do_not_affect_graph_identity(self):
        hints=[{"venue":"orca","address":"a"*40},
               {"venue":"raydium_cpmm","address":"b"*40}]
        mint="z"*44
        evidence=[{"venue":h["venue"],"address":h["address"],
                   "mints":[SOL,mint],"verified":True,"slot":123,
                   "vault_base_units":[1,1]} for h in hints]
        r=reconcile(hints,evidence,target=1)
        self.assertEqual(len(r["cross_venue_shared_pairs"]),1)
        self.assertIn(mint, r["graph_pools"][0]["mints"])
        self.assertIn("zzzzzzzz",r["graph_pools"][0]["pair"])
        self.assertGreater(discover_cycles(r["graph_pools"],min_hops=2,max_hops=2)["cycle_count"],0)

if __name__=="__main__":
    unittest.main()
