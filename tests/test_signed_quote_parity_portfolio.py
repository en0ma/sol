import unittest
from unittest.mock import patch
from arb.signed_quote_parity_portfolio import evaluate_cases
def case():
 return {"fixture":{"first_venue":"orca","second_venue":"raydium_cpmm","first_pool":"p","second_pool":"q","state_account_manifest_sha256":"x"},
 "route":{"start_mint":"A"},"quotes":[{"amount_in":100},{"amount_in":80}],"receipt":{}}
class Tests(unittest.TestCase):
 def test_nonempty_bounded_batch(self):
  with self.assertRaises(ValueError):evaluate_cases([],as_of_unix=1)
 def test_duplicate_fixtures_rejected(self):
  a=case()
  with patch("arb.signed_quote_parity_portfolio.compare",return_value={"first_leg_deviation_bps":10,"second_leg_deviation_bps":20,"signed_atomic_evidence_status":"VERIFIED","provenance_status":"UNVERIFIED"}):
   with self.assertRaises(ValueError):evaluate_cases([a,a],as_of_unix=1)
 def test_empirical_deviation_not_trading_approval(self):
  with patch("arb.signed_quote_parity_portfolio.compare",return_value={"first_leg_deviation_bps":10,"second_leg_deviation_bps":20,"signed_atomic_evidence_status":"VERIFIED","provenance_status":"UNVERIFIED"}):
   r=evaluate_cases([case()],as_of_unix=1)
  self.assertTrue(r["rows"][0]["within_declared_tolerance_diagnostic"])
  self.assertEqual(r["validated_accuracy_samples"],0)
  self.assertEqual(r["rows"][0]["cost_research_status"],"UNASSESSABLE_MISSING_COSTS")
  self.assertFalse(r["rows"][0]["profitability_confirmed"])
if __name__=="__main__":unittest.main()
