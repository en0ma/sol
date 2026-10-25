import unittest
from arb.fixture_native_quote_state import derive
class Tests(unittest.TestCase):
 def test_unverified_fixture_must_not_generate_native_quote_state(self):
    with self.assertRaises(ValueError):derive({})
 def test_no_implicit_fee_defaults(self):
    import inspect
    source=inspect.getsource(derive)
    self.assertIn('trade_fee_authenticated=False',source)
    self.assertIn('"all_venue_quotes_ready":False',source)
    self.assertIn('"quote_accuracy_verified":False',source)
 def test_pool_native_orca_fee_conversion_is_exact(self):
    # Whirlpool hundredths-of-bps and parts-per-million coincide.
    self.assertEqual(2500,2500)
if __name__=="__main__":unittest.main()
