import unittest
from arb.fixture_config_quote_projection import derive,quote_cpmm_only
class Tests(unittest.TestCase):
 def test_untrusted_source_refused(self):
  with self.assertRaises(ValueError):derive({},observed_unix=123)
 def test_invalid_observation_refused(self):
  for value in (True,-1,"123"):
   with self.assertRaises(ValueError):derive({},observed_unix=value)
 def test_cpmm_quote_cannot_come_from_empty_fixture(self):
  with self.assertRaises(ValueError):
   quote_cpmm_only({},observed_unix=123,leg={"venue":"raydium_cpmm","pool":"x"},amount_in=1)
 def test_partial_source_quote_never_claims_execution(self):
  import inspect
  s=inspect.getsource(derive)+inspect.getsource(quote_cpmm_only)
  self.assertIn('"full_seven_venue_pricing_verified":False',s)
  self.assertIn('"signed_execution_reconciled":False',s)
if __name__=="__main__":unittest.main()
