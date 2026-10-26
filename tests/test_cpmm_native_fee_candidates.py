import unittest
from arb.cpmm_quote import quote_native_fee_candidates
class Tests(unittest.TestCase):
 def test_fractional_and_integer_candidates_distinct_on_dust(self):
  found=False
  for n in range(1,100):
   try:q=quote_native_fee_candidates(1000,10000,n,2500)
   except ValueError:continue
   self.assertLessEqual(q["ceil_fee_then_swap_output_base_units"],q["floor_fee_then_swap_output_base_units"])
   if q["fractional_invariant_output_base_units"] != q["floor_fee_then_swap_output_base_units"]:found=True
  self.assertTrue(found)
 def test_reject_invalid(self):
  with self.assertRaises(ValueError):
   quote_native_fee_candidates(0,1000,10,2500)
if __name__=="__main__":unittest.main()
