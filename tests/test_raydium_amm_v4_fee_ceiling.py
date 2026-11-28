"""AMM v4 ceiling fee math using minimized real source constants.
Source fixture BZ5-01, run 46083652900, source slot 474738617.
Not a fresh signed receipt; exact observed inputs and adjusted reserve values.
"""
import unittest
from unittest.mock import patch
from arb.raydium_amm_v4_fee_state import quote_native_fraction
from arb.raydium_amm_v4_fixture_quote import quote_from_fixture

class AmmV4FeeCeiling(unittest.TestCase):
    def test_captured_integer_fee_matches_signed_outputs(self):
        reserves=[524410002524,680532974426]
        for amount,fee,expected in ((5133,13,6644),(51269,129,66364)):
            with self.subTest(amount=amount):
                q=quote_native_fraction(reserves,["A","B"],"A",amount,25,10000)
                self.assertEqual(q["fee_ceiling_input_units"],fee)
                self.assertEqual(q["protocol_fee_ceiling_amount_out"],expected)
        self.assertEqual(q["rational_fee_reference_amount_out"],66366)

    def test_fixture_adapter_selects_ceiling_not_rational(self):
        row={"address":"p","mints":["A","B"],"slot":12,
             "market_accounts_authenticated":True,"effective_reserves_authenticated":True,
             "native_fraction_fee_authenticated":True,"trade_fee_authenticated":False,
             "effective_reserves_base_units":[524410002524,680532974426],
             "native_fee_numerator":25,"native_fee_denominator":10000}
        with patch("arb.raydium_amm_v4_fixture_quote.derive_v4",return_value={"pricing":[row]}):
            q=quote_from_fixture({},pool="p",input_mint="A",amount_in=51269,observed_unix=10)
        self.assertEqual(q["quote"]["amount_out"],66364)
        self.assertEqual(q["quote"]["rational_fee_reference_amount_out"],66366)
        self.assertFalse(q["signed_swap_accuracy_verified"])

if __name__=="__main__":unittest.main()
