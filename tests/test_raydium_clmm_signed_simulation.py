import unittest
from unittest.mock import patch
from arb.raydium_clmm_signed_simulation import simulate_signed
from arb.raydium_clmm import PROGRAM
from arb.token_vaults import TOKEN_PROGRAM


class SignedClmmSimulationTests(unittest.TestCase):
    args=("http://127.0.0.1:8899",b"signed","in","out","mintA","mintB",
          1000,100,300,200)

    @patch("arb.raydium_clmm_signed_simulation.call")
    def test_remote_endpoint_rejected_before_network(self,call):
        with self.assertRaises(ValueError):
            simulate_signed("https://mainnet.example",*self.args[1:])
        call.assert_not_called()

    @patch("arb.raydium_clmm_signed_simulation.decode_token_account")
    @patch("arb.raydium_clmm_signed_simulation.call")
    def test_verified_deltas_not_profit_claim(self,call,decode):
        call.return_value={"value":{"err":None,"logs":[
            "Program "+PROGRAM+" invoke [1]"],"unitsConsumed":45000,
            "accounts":[{"owner":TOKEN_PROGRAM,"data":["AA==","base64"]},
                        {"owner":TOKEN_PROGRAM,"data":["AA==","base64"]}]}}
        decode.side_effect=[{"mint":"mintA","amount_base_units":700},
                            {"mint":"mintB","amount_base_units":320}]
        report=simulate_signed(*self.args)
        self.assertEqual(report["spent_base_units"],300)
        self.assertEqual(report["received_base_units"],220)
        self.assertTrue(report["simulation_verified"])
        self.assertFalse(report["profitable_arbitrage_verified"])

    @patch("arb.raydium_clmm_signed_simulation.call")
    def test_rpc_error_fails_closed(self,call):
        call.return_value={"value":{"err":{"InstructionError":[0,"Custom"]}}}
        with self.assertRaisesRegex(ValueError,"simulation failed"):
            simulate_signed(*self.args)

    @patch("arb.raydium_clmm_signed_simulation.call")
    def test_non_clmm_invocation_rejected(self,call):
        call.return_value={"value":{"err":None,"logs":["unrelated"],"accounts":[]}}
        with self.assertRaisesRegex(ValueError,"invocation missing"):
            simulate_signed(*self.args)
