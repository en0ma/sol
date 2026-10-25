import unittest
from unittest.mock import patch
from arb.quote_simulation_reconciliation import reconcile
route={"legs":[{"venue":"raydium_cpmm","pool":"p","input_mint":"A","output_mint":"B"},{"venue":"raydium_clmm","pool":"q","input_mint":"B","output_mint":"A"}]}
quotes=[{"venue":"raydium_cpmm","pool":"p","input_mint":"A","output_mint":"B","snapshot_slot":7,"amount_in":100,"amount_out":80},{"venue":"raydium_clmm","pool":"q","input_mint":"B","output_mint":"A","snapshot_slot":7,"amount_in":80,"amount_out":110}]
def receipt(remaining):
 return {"route_pool_addresses":["p","q"],"route_mints":["A","B","A"],"source_snapshot_slot":7,"initial_balances_base_units":[100,0,0],"positive_post_balances_base_units":[0,remaining,110],"first_leg_intermediate_received_base_units":80}
class Tests(unittest.TestCase):
 def test_matching_intermediate(self):
  with patch("arb.quote_simulation_reconciliation.assess",return_value={"status":"VERIFIED"}):
   r=reconcile(route,quotes,receipt(0))
  self.assertEqual(r["status"],"RECONCILED_SIGNED_SIMULATION")
  self.assertEqual(r["signed_intermediate_consumed_base_units"],80)
 def test_fixed_second_leg_mismatch(self):
  with patch("arb.quote_simulation_reconciliation.assess",return_value={"status":"VERIFIED"}):
   r=reconcile(route,quotes,receipt(30))
  self.assertEqual(r["status"],"UNVERIFIED")
if __name__=="__main__":unittest.main()
