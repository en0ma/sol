"""Second independently authenticated source case: 2-point DBC curve.

Source: actions run 40908174752, original raw config and SDK quote artifact
12911659087. Raw state hashes remain in the artifact; these are exact
integer reference vectors for the native bounded two-point walk.
"""
import unittest
from arb.meteora_dbc_native_curve_walk import walk

PRICE=3864292729849665123
START=1996138205418331300
MIGRATION=7638419735324145379
CURVE=[
    (7638419735324145379,2142451999766302688009391078713577),
    (79226673521066979257578248091,2821319075291600657604802),
]


class DbCTwoPointRealSourceVectors(unittest.TestCase):
    def test_exact_four_original_reference_curve_outputs(self):
        tests=[
            (True,481124372,3864289376445375842,21113370),
            (True,4811243720,3864259196068675588,211132057),
            (False,11703277,3864294588663210876,266689971),
            (False,117032775,3864311317985916796,2666888281),
        ]
        for base,amount,next_price,gross in tests:
            with self.subTest(base_for_quote=base,input=amount):
                r=walk(sqrt_price=PRICE,amount_in=amount,
                       base_for_quote=base,curve=CURVE,
                       sqrt_start_price=START,migration_sqrt_price=MIGRATION)
                self.assertEqual(r["next_sqrt_price"],next_price)
                self.assertEqual(r["output_amount"],gross)
                self.assertFalse(r["signed_verified"])

    def test_bounded_invalid_curve_rejected(self):
        with self.assertRaisesRegex(ValueError,"not increasing"):
            walk(sqrt_price=PRICE,amount_in=10,base_for_quote=True,
                 curve=list(reversed(CURVE)),
                 sqrt_start_price=START,migration_sqrt_price=MIGRATION)


if __name__=="__main__":unittest.main()
