import unittest
from arb.fixture_tick_coverage import coverage
class Tests(unittest.TestCase):
 def test_missing_fixture_rejected(self):
  with self.assertRaises(ValueError):coverage({})
 def test_coverage_never_fabricates_tick_liquidity(self):
  import inspect
  s=inspect.getsource(coverage)
  self.assertIn('"complete_directional_price_coverage_verified":False',s)
  self.assertIn('"swap_output_parity_verified":False',s)
if __name__=="__main__":unittest.main()
