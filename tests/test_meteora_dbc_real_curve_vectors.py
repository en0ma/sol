"""Independent DBC curve vectors from authenticated 2026-10-29 real SDK run.

The raw config digest and original bytes are retained in Actions artifact
12907694995; these vectors test curve math ONLY (not fee scheduler/signed swap).
"""
import unittest
from arb.meteora_dbc_native_segment import quote_one_segment

PRICE=92098360923781808
LIQUIDITY=100276303319821972080827062311934
START=91919944922729045
STOP=318420028436199832


class DbcRealSourceCurveVectors(unittest.TestCase):
    def test_real_original_source_curve_matches_four_reference_prices(self):
        vectors=(
            (True,997886654,92098276515258379,24873),
            (True,9978866540,92097516845509924,248737),
            (False,9699,92098393836828734,389101089),
            (False,96998,92098690081398651,3891319319),
        )
        for base,amount,expected_next,expected_gross in vectors:
            with self.subTest(base=base,amount=amount):
                result=quote_one_segment(sqrt_price=PRICE,
                      liquidity=LIQUIDITY,input_amount=amount,
                      base_for_quote=base,
                      target_price=START if base else STOP)
                self.assertEqual(result["next_sqrt_price"],expected_next)
                self.assertEqual(result["output_amount"],expected_gross)
                self.assertFalse(result["full_pool_sdk_parity"])
                self.assertFalse(result["signed_verified"])


if __name__=="__main__":unittest.main()
