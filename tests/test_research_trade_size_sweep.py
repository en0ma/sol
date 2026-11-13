import unittest
from arb.research_trade_size_sweep import sweep
POOL={"venue":"raydium_cpmm","address":"one","mints":["A","B"],
"vault_base_units":[100000,200000],"trade_fee_ppm":2500,"trade_fee_authenticated":True,
"verified":True,"account_owner_verified":True,"source_authenticated":True,
"snapshot_origin":"READ_ONLY_MAINNET_BACKED_SURFPOOL","slot":500,"observed_unix":990}
OTHER={**POOL,"address":"two","vault_base_units":[200000,100000]}
COSTS={"network_fee":1,"priority_fee":1,"compute_cost":1,
"slippage_buffer":1,"quote_uncertainty_buffer":1}
class Tests(unittest.TestCase):
 def test_each_size_is_requoted_and_stays_simulation_only(self):
    result=sweep([POOL,OTHER],as_of_unix=1000,input_sizes=[2000,1000],
                 cost_provider=lambda route,quotes:COSTS)
    self.assertEqual([x["input_base_units"] for x in result["size_reports"]],[1000,2000])
    self.assertFalse(result["actionable"])
    self.assertEqual(result["verified_profitable_opportunities"],0)
    self.assertEqual(result["sizes_tested"],2)
 def test_no_fake_costs_or_positive_profit(self):
    result=sweep([POOL,OTHER],as_of_unix=1000,input_sizes=[1000],
                 cost_provider=lambda *x:None)
    self.assertEqual(result["positive_declared_cost_estimates"],0)
 def test_reject_duplicate_or_invalid_trade_sizes(self):
    for amounts in ([0],[100,100],[],list(range(1,18))):
      with self.assertRaises(ValueError):
        sweep([POOL,OTHER],as_of_unix=1000,input_sizes=amounts,
              cost_provider=lambda *x:COSTS)
 def test_stale_pool_does_not_produce_opportunities(self):
    result=sweep([dict(POOL,observed_unix=1),OTHER],
        as_of_unix=1000,input_sizes=[1000],cost_provider=lambda *x:COSTS)
    self.assertEqual(result["positive_declared_cost_estimates"],0)
if __name__=="__main__":unittest.main()
