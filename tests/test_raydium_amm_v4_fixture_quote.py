import unittest
from arb.raydium_amm_v4_fixture_quote import quote_from_fixture
class Tests(unittest.TestCase):
 def test_invalid_source_fails(self):
  with self.assertRaises(ValueError):
   quote_from_fixture({},pool="x",input_mint="y",amount_in=1,observed_unix=1)
 def test_invalid_clock_fails(self):
  for now in (True,-1,"1"):
   with self.assertRaises(ValueError):
    quote_from_fixture({},pool="x",input_mint="y",amount_in=1,observed_unix=now)
 def test_indicative_only(self):
  import inspect
  source=inspect.getsource(quote_from_fixture)
  self.assertIn('"signed_swap_accuracy_verified":False',source)
  self.assertIn('"source_rpc_provenance_independently_attested":False',source)
  self.assertIn('from_snapshot([record]',source)
if __name__=="__main__":unittest.main()
