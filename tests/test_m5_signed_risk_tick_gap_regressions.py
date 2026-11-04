import unittest
from unittest.mock import patch
from arb.signed_parity_risk_report import report
from arb.fixture_tick_coverage import coverage
C={"network_fee":1,"priority_fee":1,"compute_cost":1,"slippage_buffer":1,"quote_uncertainty_buffer":1}
CASE={"receipt":{"initial_balances_base_units":[100,0,0],"positive_post_balances_base_units":[0,0,120]},"quotes":[{"amount_in":100},{"amount_out":120}],"costs_start_mint_units":C}
class Tests(unittest.TestCase):
 def test_unsigned_observed_balances_cannot_become_risk_evidence(self):
  with patch("arb.signed_parity_risk_report.evaluate_cases",return_value={"rows":[{"signed_atomic_evidence_status":"UNVERIFIED"}]}):
   out=report([CASE],as_of_unix=123)
  self.assertIsNone(out["rows"][0]["observed_risk"])
  self.assertFalse(out["rows"][0]["signed_observation_supported"])
 def test_all_missing_intermediate_arrays_reported(self):
  fixture={}
  pool={"venue":"orca","pool":"p","tick_current":1,"tick_arrays":[{"start_tick":0},{"start_tick":352}],"initialized_ticks":[]}
  with patch("arb.fixture_tick_coverage.extract",return_value={"pools":[pool]}),patch("arb.fixture_quote_execution_pipeline.extract_pool_states",return_value=[{"address":"p","decoded_pool_state":{"tick_spacing":1}}]):
   out=coverage(fixture)
  self.assertEqual(out["rows"][0]["missing_intermediate_array_starts"],[88,176,264])
  self.assertFalse(out["rows"][0]["complete_directional_price_coverage_verified"])
if __name__=="__main__":unittest.main()
