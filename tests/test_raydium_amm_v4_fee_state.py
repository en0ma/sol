import unittest
from arb.raydium_amm_v4_fee_state import fee_from_raw_pool,derive_v4
class Tests(unittest.TestCase):
 def test_invalid_account_refused(self):
  with self.assertRaises(ValueError):fee_from_raw_pool(b"")
 def test_unverified_source_refused(self):
  with self.assertRaises(ValueError):derive_v4({})
 def test_no_quote_parity_self_certification(self):
  import inspect
  self.assertIn('"signed_quote_parity_verified":False',inspect.getsource(derive_v4))
if __name__=="__main__":unittest.main()
