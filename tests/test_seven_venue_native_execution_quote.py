import unittest
from unittest.mock import patch

from arb.seven_venue_native_execution_quote import (
    quote_signed_single_leg, VENUES)

class NativeExecutionQuoteTests(unittest.TestCase):
    def test_supports_all_seven_native_adapters_without_mainnet_broadcast(self):
        self.assertEqual(VENUES, frozenset((
            "orca","raydium_cpmm","raydium_clmm","meteora_dlmm",
            "meteora_damm_v2","pumpswap","raydium_amm_v4")))
        with self.assertRaises(ValueError):
            quote_signed_single_leg(
                "https://api.mainnet-beta.solana.com",
                venue="orca",pool="p"*44,state={},evidence={},
                signer=object(),input_token_account="a"*44,
                output_token_account="b"*44,input_mint="c"*44,
                output_mint="d"*44,initial_input_base_units=100,
                initial_output_base_units=0,amount_in_base_units=50)

    def test_missing_funding_and_unsupported_venue_rejected_before_builder(self):
        args=dict(rpc="http://127.0.0.1:8899",venue="orca",pool="p"*44,
                  state={},evidence={},signer=object(),
                  input_token_account="a"*44,output_token_account="b"*44,
                  input_mint="c"*44,output_mint="d"*44,
                  initial_input_base_units=100,initial_output_base_units=0,
                  amount_in_base_units=101)
        with patch("arb.seven_venue_native_execution_quote.build_leg") as builder:
            with self.assertRaises(ValueError):
                quote_signed_single_leg(**args)
            args.update(amount_in_base_units=99,venue="fake")
            with self.assertRaises(ValueError):
                quote_signed_single_leg(**args)
            builder.assert_not_called()

if __name__=="__main__":
    unittest.main()
