import unittest
from unittest.mock import patch
from arb.m5_three_venue_signed_quote_parity import compare
class Tests(unittest.TestCase):
 @patch("arb.m5_three_venue_signed_quote_parity.accept",return_value=True)
 @patch("arb.m5_three_venue_signed_quote_parity.quote_cpmm_only")
 def test_source_fee_models_vs_signed_output(self,quote,_):
  fixture={"route_mints":["A","B","C","A"],"route_venues":["raydium_cpmm","orca","raydium_amm_v4"],
   "route_pool_addresses":["cp","or","v4"],"state_accounts_observed_slot":9}
  receipt={"planned_inputs":[100,90,80],"initial_balances_base_units":[100,0,0,0],
   "positive_post_balances_base_units":[0,0,0,120],
   "cpi_hops":[{"hop":1,"received_base_units":90,"consumed_base_units":90},
               {"hop":2,"received_base_units":80,"consumed_base_units":80}]}
  quote.return_value={"quote":{"venue":"raydium_cpmm","pool":"cp","input_mint":"A",
   "output_mint":"B","amount_in":100,"amount_out":89,"snapshot_slot":9},
   "native_fee_candidate_quotes":{"fractional_invariant_output_base_units":89,
     "floor_fee_then_swap_output_base_units":90,
     "ceil_fee_then_swap_output_base_units":89}}
  r=compare(fixture,receipt,observed_unix=1)
  self.assertIn("floor_fee_then_swap",r["leg_comparisons"][0]["cpmm_signed_output_matches_fee_model"])
  self.assertNotIn("fractional_invariant",r["leg_comparisons"][0]["cpmm_signed_output_matches_fee_model"])
  self.assertFalse(r["leg_comparisons"][0]["quote_verified"])
if __name__=="__main__":unittest.main()
