import unittest
from arb.raydium_amm_v4_fee_state import quote_native_fraction
class Tests(unittest.TestCase):
    def test_native_fraction_directions_and_non_ppm_precision(self):
        a=quote_native_fraction([100000,200000],["A","B"],"A",1000,1,3000)
        b=quote_native_fraction([100000,200000],["A","B"],"B",1000,1,3000)
        self.assertEqual(a["fee_numerator"],1)
        self.assertEqual(a["fee_denominator"],3000)
        self.assertTrue(a["amount_out"]>b["amount_out"])
        self.assertEqual(a["fee_floor_input_units"],0)
        self.assertEqual(a["fee_ceiling_input_units"],1)
    def test_invalid_fee_fraction_and_mint_rejected(self):
        for args in ((1,1),(0,100),(4,3)):
            with self.subTest(args=args),self.assertRaises(ValueError):
                quote_native_fraction([100,200],["A","B"],"A",10,*args)
        with self.assertRaises(ValueError):
            quote_native_fraction([100,200],["A","B"],"C",10,1,100)
if __name__=="__main__":unittest.main()
