import unittest
from unittest.mock import patch
from arb.venue_signed_quote_experiments import measure
class Tests(unittest.TestCase):
 @patch("arb.venue_signed_quote_experiments.compare")
 def test_only_actual_accepted_signed_cpi_becomes_comparison(self,compare):
  compare.return_value={"signed_execution_accepted":True,
   "leg_comparisons":[{"venue":"raydium_cpmm","pool":"P","leg_index":0,
     "signed_input_base_units":100,"signed_output_base_units":95,
     "quoted_output_base_units":94,"signed_minus_quote_base_units":1,
     "reason":"INDICATIVE_ONLY_SOURCE_EXECUTION_PROVENANCE_NOT_INDEPENDENTLY_VERIFIED"},
    {"venue":"orca","pool":"O","leg_index":1,
     "signed_input_base_units":95,"signed_output_base_units":80,
     "quoted_output_base_units":None,"reason":"SOURCE_EXACT_QUOTE_BLOCKED"}]}
  x=measure({"state_account_manifest_sha256":"manifest",
    "state_accounts_observed_slot":42},{},observed_unix=1)
  self.assertEqual(x["observed_compared_samples"],1)
  self.assertEqual(x["exact_integer_matches"],0)
  self.assertEqual(x["venue_samples"][0]["integer_delta_base_units"],1)
  self.assertEqual(x["venue_samples"][1]["sample_status"],"SAMPLE_BLOCKED")
  self.assertEqual(x["independently_validated_protocol_exact_samples"],0)
 @patch("arb.venue_signed_quote_experiments.compare")
 def test_unaccepted_or_fake_signed_swaps_do_not_count(self,compare):
  compare.return_value={"signed_execution_accepted":False,
   "leg_comparisons":[{"venue":"raydium_cpmm","pool":"P","leg_index":0,
    "signed_input_base_units":100,"signed_output_base_units":95,
    "quoted_output_base_units":95,"signed_minus_quote_base_units":0}]}
  x=measure({}, {},observed_unix=1)
  self.assertEqual(x["observed_compared_samples"],0)
  self.assertEqual(x["exact_integer_matches"],0)
if __name__=="__main__":unittest.main()
