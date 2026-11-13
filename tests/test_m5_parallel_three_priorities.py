import unittest
from arb.observed_signed_risk import screen
from arb.fixture_missing_tick_arrays import missing_arrays
from arb.signed_parity_risk_report import report
from unittest.mock import patch
C={"network_fee":2,"priority_fee":1,"compute_cost":1,"slippage_buffer":2,"quote_uncertainty_buffer":3}
class Tests(unittest.TestCase):
 def test_observed_net_respects_all_costs_and_never_certifies_profit(self):
  r=screen(input_units=100,observed_output_units=112,quoted_output_units=114,costs=C)
  self.assertEqual(r["observed_net_after_declared_costs_start_mint_units"],3)
  self.assertFalse(r["profitability_confirmed"])
 def test_missing_cost_blocked(self):
  with self.assertRaises(ValueError):screen(input_units=100,observed_output_units=112,quoted_output_units=114,costs={})
 def test_invalid_tick_source_blocked(self):
  with self.assertRaises(ValueError):missing_arrays({})
 def test_batch_does_not_validate_observed_diagnostic(self):
  item={"receipt":{"initial_balances_base_units":[100,0,0],"positive_post_balances_base_units":[0,0,112]},
        "quotes":[{"amount_in":100},{"amount_out":114}],"costs_start_mint_units":C}
  with patch("arb.signed_parity_risk_report.evaluate_cases",return_value={"rows":[{"signed_atomic_evidence_status":"VERIFIED"}]}):
   out=report([item],as_of_unix=1)
  self.assertEqual(out["rows"][0]["observed_risk"]["observed_net_after_declared_costs_start_mint_units"],3)
  self.assertFalse(out["rows"][0]["real_profitability_verified"])
if __name__=="__main__":unittest.main()
