import unittest
from unittest.mock import patch
from arb.signed_quote_accuracy_report import compare
from arb.source_snapshot_manifest import digest
class Tests(unittest.TestCase):
 def test_measures_both_legs_without_self_certifying(self):
  a={"x":{"owner":"x","data":["AA==","base64"]}}
  f={"accounts":a,"state_account_addresses":["x"],"state_account_count":1,
     "state_accounts_observed_slot":7,"state_account_manifest_sha256":digest(a,["x"],7),
     "first_pool":"p","second_pool":"q","route_mints":["A","B","A"]}
  quotes=[{"amount_in":100,"amount_out":80},{"amount_in":80,"amount_out":110}]
  receipt={"first_leg_intermediate_received_base_units":79,
           "initial_balances_base_units":[100,0,0],
           "positive_post_balances_base_units":[0,0,105]}
  with patch("arb.signed_quote_accuracy_report.reconcile",return_value={
       "signed_atomic_evidence_status":"UNVERIFIED","status":"UNVERIFIED"}):
   result=compare(f,{},quotes,receipt)
  self.assertEqual(result["first_leg_deviation_bps"],125)
  self.assertEqual(result["second_leg_deviation_bps"],454)
  self.assertFalse(result["real_quote_accuracy_verified"])
 def test_missing_quotes_rejected(self):
  with self.assertRaises(ValueError):compare({}, {}, [], {})
if __name__=="__main__":unittest.main()
