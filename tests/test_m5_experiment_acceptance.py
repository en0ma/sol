import unittest
from unittest.mock import patch
from arb.m5_experiment_acceptance import assess_experiment
C={"network_fee":1,"priority_fee":1,"compute_cost":1,"slippage_buffer":1,"quote_uncertainty_buffer":1}
class Tests(unittest.TestCase):
 def test_failed_signed_evidence_blocks_risk_even_if_fake_balances_positive(self):
  with patch("arb.m5_experiment_acceptance.compare",return_value={"signed_atomic_evidence_status":"UNVERIFIED","provenance_status":"UNVERIFIED"}):
   out=assess_experiment({"first_venue":"raydium_cpmm","second_venue":"raydium_amm_v4"},{},[],{"initial_balances_base_units":[100,0,0],"positive_post_balances_base_units":[0,0,200]},costs=C)
  self.assertIsNone(out["cost_risk_diagnostic"])
  self.assertFalse(out["real_profitability_confirmed"])
 def test_good_offline_evidence_does_not_authorize_trade(self):
  with patch("arb.m5_experiment_acceptance.compare",return_value={"signed_atomic_evidence_status":"VERIFIED","provenance_status":"PROVENANCE_FIELDS_CONSISTENT_NOT_INDEPENDENTLY_ATTESTED"}):
   out=assess_experiment({"first_venue":"raydium_cpmm","second_venue":"raydium_amm_v4"},{},[],{"initial_balances_base_units":[100,0,0],"positive_post_balances_base_units":[0,0,110]},costs=C)
  self.assertEqual(out["cost_risk_diagnostic"]["conservative_net_start_mint_units"],3)
  self.assertFalse(out["signed_swap_quote_accuracy_independently_validated"])
  self.assertFalse(out["actionable"])
if __name__=="__main__":unittest.main()
