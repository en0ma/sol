import unittest
from arb.snapshot_research_runner import run_authenticated_snapshot
S={"venue":"raydium_cpmm","address":"p1","mints":["A","B"],
"vault_base_units":[100000,200000],"trade_fee_ppm":2500,"trade_fee_authenticated":True,
"verified":True,"account_owner_verified":True,"source_authenticated":True,
"snapshot_origin":"READ_ONLY_MAINNET_BACKED_SURFPOOL","slot":500,"observed_unix":990}
T={**S,"address":"p2","vault_base_units":[200000,100000]}
C={"network_fee":2,"priority_fee":2,"compute_cost":2,
"slippage_buffer":5,"quote_uncertainty_buffer":5}
class IntegrationTests(unittest.TestCase):
 def test_real_cpmm_quotes_feed_graph_screening_and_no_execution(self):
    result=run_authenticated_snapshot([S,T],as_of_unix=1000,initial_input=1000,
        cost_provider=lambda route,quotes:C)
    self.assertGreater(result["graph_cycles"],0)
    self.assertGreater(result["screened_routes"],0)
    self.assertEqual(result["signed_simulated_candidates"],0)
    self.assertFalse(result["broadcast"])
    self.assertTrue(any(x.get("research",{}).get("gross_start_mint_units") is not None
                        for x in result["results"]))
 def test_missing_cost_provider_never_fabricates_profit(self):
    result=run_authenticated_snapshot([S,T],as_of_unix=1000,initial_input=1000,
        cost_provider=lambda *x:None)
    self.assertEqual(result["research_positive"],0)
 def test_no_stale_snapshot_bypass(self):
    result=run_authenticated_snapshot([dict(S,observed_unix=10),T],
        as_of_unix=1000,initial_input=1000,cost_provider=lambda *x:C)
    self.assertEqual(result["graph_cycles"],0)
    self.assertEqual(len(result["snapshot_rejected_pools"]),1)
 def test_input_and_unintegrated_venue_fail_closed(self):
    with self.assertRaises(ValueError):
      run_authenticated_snapshot([S,T],as_of_unix=1000,initial_input=0,
        cost_provider=lambda *x:C)
if __name__=="__main__":unittest.main()
