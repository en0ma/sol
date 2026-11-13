import unittest
from unittest.mock import patch
from arb.raydium_amm_v4_fixture_quote import quote_from_fixture
class Tests(unittest.TestCase):
    @patch("arb.raydium_amm_v4_fixture_quote.derive_v4")
    def test_non_ppm_fraction_still_quotes_native_source_reserves(self,derive):
        derive.return_value={"pricing":[{"address":"pool","mints":["A","B"],
          "slot":77,"native_fee_numerator":1,"native_fee_denominator":3000,
          "native_fraction_fee_authenticated":True,"trade_fee_authenticated":False,
          "market_accounts_authenticated":True,"effective_reserves_authenticated":True,
          "effective_reserves_base_units":[100000,200000]}]}
        q=quote_from_fixture({},pool="pool",input_mint="A",amount_in=1000,observed_unix=12)
        self.assertGreater(q["quote"]["amount_out"],0)
        self.assertEqual(q["quote"]["quote_model"],"AMM_V4_NATIVE_FRACTION_ADJUSTED_RESERVE_INDICATIVE")
        self.assertFalse(q["signed_swap_accuracy_verified"])
    @patch("arb.raydium_amm_v4_fixture_quote.derive_v4")
    def test_no_market_authentication_never_quoted(self,derive):
        derive.return_value={"pricing":[{"address":"pool","mints":["A","B"],
          "slot":77,"native_fee_numerator":1,"native_fee_denominator":3000,
          "native_fraction_fee_authenticated":True,"trade_fee_authenticated":False,
          "market_accounts_authenticated":False,"effective_reserves_authenticated":True,
          "effective_reserves_base_units":[100000,200000]}]}
        with self.assertRaises(ValueError):
            quote_from_fixture({},pool="pool",input_mint="A",amount_in=1000,observed_unix=12)
if __name__=="__main__":unittest.main()
