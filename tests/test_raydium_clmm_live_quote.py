import unittest
from unittest.mock import patch
from arb.raydium_clmm_live_quote import quote_live


class ClmmLiveQuoteTests(unittest.TestCase):
    @patch("arb.raydium_clmm_live_quote.read")
    def test_remote_rpc_rejected(self,read):
        with self.assertRaises(ValueError):
            quote_live("https://example.com","pool","SOL",1000)
        read.assert_not_called()

    @patch("arb.raydium_clmm_live_quote.quote_within_tick")
    @patch("arb.raydium_clmm_live_quote.inspect_authenticated")
    @patch("arb.raydium_clmm_live_quote.read")
    def test_within_tick_quote_remains_indicative(self,read,inspect,quote):
        state={"token_mint_0":"SOL","token_mint_1":"USDC"}
        read.return_value={"state":state,"slot":100,"trade_fee_rate_ppm":3000}
        inspect.return_value={"boundary_observed":True,"boundary_sqrt_x64":300,
                              "fee_rate_ppm":3000,"slot":100}
        quote.return_value={"status":"INDICATIVE_WITHIN_TICK_ONLY",
                            "estimated_output_base_units":990}
        result=quote_live("http://127.0.0.1:8899","pool","SOL",1000)
        quote.assert_called_once_with(state,"SOL",1000,3000,300)
        self.assertFalse(result["executable_quote"])
        self.assertFalse(result["actionable"])

    @patch("arb.raydium_clmm_live_quote.inspect_authenticated")
    @patch("arb.raydium_clmm_live_quote.read")
    def test_cross_slot_snapshot_rejected(self,read,inspect):
        read.return_value={"state":{"token_mint_0":"SOL","token_mint_1":"USDC"},
                           "slot":100,"trade_fee_rate_ppm":3000}
        inspect.return_value={"boundary_observed":True,"boundary_sqrt_x64":300,
                              "fee_rate_ppm":3000,"slot":101}
        with self.assertRaisesRegex(ValueError,"non-atomic"):
            quote_live("http://127.0.0.1:8899","pool","SOL",1000)
