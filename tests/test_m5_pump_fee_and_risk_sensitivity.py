import unittest
from arb.pumpswap_captured_fee_state import inspect
from arb.offline_risk_sensitivity import sensitivity
class Tests(unittest.TestCase):
 def test_invalid_pump_source_refused(self):
  with self.assertRaises(ValueError):inspect({},config_address="a")
 def test_extra_slippage_can_erase_net_profit(self):
  r=sensitivity(input_units=1000,observed_output_units=1020,declared_cost_units=10,extra_uncertainty_bps=200)
  self.assertEqual(r["additional_adverse_output_units"],21)
  self.assertEqual(r["conservative_net_start_mint_units"],-11)
  self.assertFalse(r["profitability_confirmed"])
 def test_invalid_uncertainty_refused(self):
  with self.assertRaises(ValueError):
   sensitivity(input_units=1,observed_output_units=2,declared_cost_units=0,extra_uncertainty_bps=10001)
if __name__=="__main__":unittest.main()
