import unittest
from arb.raydium_amm_v4_fee_state import quote_native_fraction
class Tests(unittest.TestCase):
    def test_fee_floor_ceiling_bound_native_integer_output(self):
        q=quote_native_fraction([100000,200000],["A","B"],"A",1000,1,3000)
        lo,hi=q["fee_rounding_output_interval_base_units"]
        self.assertLessEqual(lo,hi)
        self.assertEqual(hi,q["integer_fee_floor_quote_output"])
        self.assertEqual(lo,q["integer_fee_ceil_quote_output"])
        self.assertGreaterEqual(q["amount_out"],lo)
        self.assertLessEqual(q["amount_out"],hi)
    def test_interval_rounding_when_fee_exact(self):
        q=quote_native_fraction([100000,200000],["A","B"],"A",1000,1,1000)
        self.assertEqual(q["fee_rounding_output_interval_base_units"][0],
                         q["fee_rounding_output_interval_base_units"][1])
if __name__=="__main__":unittest.main()
