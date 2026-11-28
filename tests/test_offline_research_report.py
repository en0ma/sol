import unittest
from arb.offline_research_report import replay
S={"venue":"raydium_cpmm","address":"p1","mints":["A","B"],"vault_base_units":[100000,200000],
"trade_fee_authenticated":True,"trade_fee_ppm":2500,"verified":True,"source_authenticated":True,
"account_owner_verified":True,"snapshot_origin":"READ_ONLY_MAINNET_BACKED_SURFPOOL",
"slot":500,"observed_unix":990}
C={"network_fee":1,"priority_fee":1,"compute_cost":1,"slippage_buffer":1,
   "quote_uncertainty_buffer":1}
class Tests(unittest.TestCase):
 def request(self):
    return {"pool_snapshots":[S,dict(S,address="p2",vault_base_units=[200000,100000])],
            "input_sizes":[500,1000],"as_of_unix":1000,
            "costs_start_mint_units":C,"costs_vary_by_size":False}
 def test_replay_explicitly_disclaims_input_authentication(self):
    r=replay(self.request())
    self.assertEqual(r["sizes_tested"],2)
    self.assertFalse(r["live_market_data_authenticated_by_replay"])
    self.assertFalse(r["signed_simulation_executed"])
    self.assertFalse(r["broadcast"])
 def test_requires_explicit_cost_assumption(self):
    x=self.request();x.pop("costs_vary_by_size")
    with self.assertRaisesRegex(ValueError,"assumption"):replay(x)
 def test_requires_costs(self):
    x=self.request();x.pop("costs_start_mint_units")
    with self.assertRaises(ValueError):replay(x)
 def test_missing_authenticated_pools_cannot_create_opportunities(self):
    x=self.request();x["pool_snapshots"]=[dict(S,account_owner_verified=False)]
    self.assertEqual(replay(x)["positive_declared_cost_estimates"],0)
if __name__=="__main__":unittest.main()
