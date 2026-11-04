import unittest
from pathlib import Path
class Tests(unittest.TestCase):
 def test_injected_pricing_decoder_cannot_self_certify_accuracy(self):
    source=Path("arb/fixture_quote_execution_pipeline.py").read_text()
    self.assertIn('"status":"UNVERIFIED_PRICING_SOURCE"',source)
    self.assertIn('"actual_pricing_state_decoder_validated":False',source)
    self.assertIn('"complete_seven_venue_accuracy_verified":False',source)
    self.assertIn('"observed_comparison_diagnostic_only":True',source)
 def test_manifest_count_must_match_exact_input_inventory(self):
    from arb.source_snapshot_manifest import digest,verify
    a={"pool":{"owner":"owner","data":["AA==","base64"]}}
    f={"accounts":a,"state_account_addresses":["pool"],"state_account_count":1,
       "state_accounts_observed_slot":42,"state_account_manifest_sha256":digest(a,["pool"],42)}
    self.assertTrue(verify(f))
    f["state_account_count"]=2
    with self.assertRaises(ValueError):verify(f)
if __name__=="__main__":unittest.main()
