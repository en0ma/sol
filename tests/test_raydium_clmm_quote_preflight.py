import unittest
from unittest.mock import patch
from arb.raydium_clmm_quote_preflight import inspect_authenticated


class ClmmQuotePreflightTests(unittest.TestCase):
    @patch("arb.raydium_clmm_quote_preflight.read")
    def test_invalid_direction_rejected_without_rpc(self,read):
        with self.assertRaisesRegex(ValueError,"direction"):
            inspect_authenticated("rpc","pool",1)
        read.assert_not_called()

    @patch("arb.raydium_clmm_quote_preflight.call")
    @patch("arb.raydium_clmm_quote_preflight.tick_array_pda",return_value="tick")
    @patch("arb.raydium_clmm_quote_preflight.read")
    def test_absent_current_array_rejected(self,read,pda,call):
        from arb.raydium_clmm_quote_preflight import PROGRAM
        import base64
        from arb.raydium_clmm_fee_snapshot import DISC
        state={"tick_current":0,"tick_spacing":64}
        read.return_value={"state":state,"slot":7,"amm_config":"config","trade_fee_rate_ppm":3000}
        with patch("arb.raydium_clmm_quote_preflight.decode",return_value=state):
            config=bytearray(53)
            config[:8]=DISC
            config[47:51]=(3000).to_bytes(4,"little")
            config[51:53]=(64).to_bytes(2,"little")
            encoded=lambda raw:{"owner":PROGRAM,"data":[base64.b64encode(raw).decode(),"base64"]}
            call.return_value={"context":{"slot":7},"value":[
                encoded(b"pool"),encoded(config),None]}
            with self.assertRaisesRegex(ValueError,"missing current"):
                inspect_authenticated("rpc","pool",True)
