import unittest
from unittest.mock import patch
from arb.venue_signed_quote_experiments import measure

class Tests(unittest.TestCase):
 @patch("arb.m5_three_distinct_venue_signed_acceptance.verify",return_value={"accepted":True})
 @patch("arb.venue_signed_quote_experiments.compare")
 def test_real_signed_route_comparison(self,compare,_verify):
  fixture={"state_account_manifest_sha256":"manifest",
   "state_accounts_observed_slot":42,
   "route_venues":["raydium_cpmm","orca","raydium_amm_v4"],
   "route_pool_addresses":["P","O","V"]}
  compare.return_value={"signed_execution_accepted":True,
   "route_venues":fixture["route_venues"],"leg_comparisons":[
    {"venue":"raydium_cpmm","pool":"P","leg_index":0,
     "signed_input_base_units":100,"signed_output_base_units":95,
     "quoted_output_base_units":94,"signed_minus_quote_base_units":1},
    {"venue":"orca","pool":"O","leg_index":1,
     "signed_input_base_units":95,"signed_output_base_units":80,
     "quoted_output_base_units":None},
    {"venue":"raydium_amm_v4","pool":"V","leg_index":2,
     "signed_input_base_units":80,"signed_output_base_units":70,
     "quoted_output_base_units":None}]}
  result=measure(fixture,{},observed_unix=1)
  self.assertEqual(result["observed_compared_samples"],1)
  self.assertEqual(result["venue_samples"][0]["integer_delta_base_units"],1)
  self.assertEqual(result["venue_samples"][1]["sample_status"],"SAMPLE_BLOCKED")
 @patch("arb.m5_three_distinct_venue_signed_acceptance.verify",return_value={"accepted":True})
 @patch("arb.venue_signed_quote_experiments.compare")
 def test_unaccepted_receipt_rejected(self,compare,_verify):
  compare.return_value={"signed_execution_accepted":False,"leg_comparisons":[]}
  with self.assertRaises(ValueError):measure({}, {},observed_unix=1)
if __name__=="__main__":unittest.main()
