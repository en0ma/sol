import unittest
from unittest.mock import patch
from arb.m5_three_venue_observed_economics import evaluate
class Tests(unittest.TestCase):
 @patch("arb.m5_three_venue_observed_economics.accept",return_value=True)
 def test_loss_must_not_be_called_profitable_at_zero_sol_fee(self,_):
  r={"planned_inputs":[100,90,80],"initial_balances_base_units":[100,0,0,0],
    "positive_post_balances_base_units":[0,0,0,95]}
  x=evaluate({"route_mints":["A","B","C","A"]},r)
  self.assertEqual(x["gross_break_even_output_deficit_base_units"],5)
  self.assertFalse(x["gross_trade_profitable_before_network_fee"])
  self.assertFalse(x["nonnegative_sol_fee_can_restore_gross_loss"])
  self.assertEqual(x["gross_delta_start_mint_base_units"],-5)
  self.assertFalse(x["profitability_verified"])
if __name__=="__main__":unittest.main()
