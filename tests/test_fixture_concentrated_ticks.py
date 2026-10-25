import unittest
from arb.fixture_concentrated_ticks import extract
class Tests(unittest.TestCase):
 def test_refuses_unverified_fixture(self):
  with self.assertRaises(ValueError):extract({})
 def test_rejects_unsupported_array_budget(self):
  with self.assertRaises(ValueError):extract({},max_arrays=0)
 def test_no_unverified_directional_coverage(self):
  import inspect
  s=inspect.getsource(extract)
  self.assertIn('"full_directional_coverage_verified":False',s)
  self.assertIn('"price_accuracy_verified":False',s)
if __name__=="__main__":unittest.main()
