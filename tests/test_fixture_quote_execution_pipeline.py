import unittest
from arb.fixture_quote_execution_pipeline import evaluate,extract_pool_states
class Tests(unittest.TestCase):
 def test_requires_explicit_account_derived_models(self):
    with self.assertRaisesRegex(ValueError,"decoder required"):
      evaluate({}, {},initial_input=100,as_of_unix=100,
               derive_pricing_state=None)
 def test_fixture_integrity_gate_before_decoder_or_quote(self):
    with self.assertRaises(ValueError):
      extract_pool_states({"state_account_addresses":["pool"],"accounts":{},
                           "state_accounts_observed_slot":42,
                           "state_account_manifest_sha256":"0"*64})
 def test_invalid_amounts_never_quoted(self):
    for amount in (0,-1,True,2**64):
      with self.assertRaises(ValueError):
       evaluate({}, {},initial_input=amount,as_of_unix=100,
                derive_pricing_state=lambda *a:{})
 def test_source_derived_state_cannot_override_identity(self):
    # Fake unverifiable fixture is rejected before supplied state could be used.
    with self.assertRaises(ValueError):
      evaluate({}, {},initial_input=100,as_of_unix=100,
               derive_pricing_state=lambda *a:{"source_authenticated":True})
if __name__=="__main__":unittest.main()
