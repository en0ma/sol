import unittest
from arb.cpmm_quote import quote_fee_rounding_interval,quote_exact_input
class Tests(unittest.TestCase):
 def test_fee_rounding_integer_envelope_both_orientations(self):
  for a,b in [(100000,200000),(200000,100000)]:
   q=quote_fee_rounding_interval(a,b,1001,2500)
   n=quote_exact_input(a,b,1001,2500)["estimated_output_base_units"]
   self.assertLessEqual(q["output_interval_base_units"][0],n)
   self.assertGreaterEqual(q["output_interval_base_units"][1],n)
   self.assertFalse(q["protocol_exact_verified"])
 def test_invalid_inputs(self):
  for x in [0,-1,2**64]:
   with self.assertRaises(ValueError):
    quote_fee_rounding_interval(100,200,x,3000)
if __name__=="__main__":unittest.main()
