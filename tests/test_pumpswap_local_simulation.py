import unittest
from unittest.mock import patch
from arb.pumpswap_local_simulation import local_rpc_only,simulate_signed


class PumpSwapLocalSimulationTests(unittest.TestCase):
    def test_reject_external_rpc(self):
        for url in ("https://api.mainnet-beta.solana.com",
                    "http://192.168.1.10:8899","http://localhost:8899@evil.com/",
                    "http://localhost:8899/proxy"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    local_rpc_only(url)
        local_rpc_only("http://127.0.0.1:8899")

    @patch("arb.pumpswap_local_simulation.call")
    def test_reject_success_without_pumpswap_invocation(self,call):
        call.return_value={"value":{"err":None,"logs":["Program unrelated invoke [1]"],
                                    "accounts":[None,None]}}
        with self.assertRaisesRegex(ValueError,"invocation"):
            simulate_signed("http://127.0.0.1:8899",b"signed",
                "user-base","user-quote","base-mint","quote-mint",100,0,50)
        self.assertEqual(call.call_args.args[1],"simulateTransaction")
        self.assertTrue(call.call_args.args[2][1]["sigVerify"])

    @patch("arb.pumpswap_local_simulation.decode_token_account")
    @patch("arb.pumpswap_local_simulation.call")
    def test_signed_success_requires_both_balance_deltas_and_output_floor(self,call,decode):
        from arb.pumpswap_pool import PROGRAM
        import base64
        from arb.token_vaults import TOKEN_PROGRAM
        account={"owner":TOKEN_PROGRAM,"data":[base64.b64encode(b"state").decode(),"base64"]}
        call.return_value={"value":{"err":None,
            "logs":["Program "+PROGRAM+" invoke [1]"],
            "accounts":[account,account]}}
        decode.side_effect=[
            {"mint":"base-mint","amount_base_units":65},
            {"mint":"quote-mint","amount_base_units":24}]
        result=simulate_signed("http://127.0.0.1:8899",b"signed",
            "user-base","user-quote","base-mint","quote-mint",100,0,50,
            min_amount_out=20)
        self.assertTrue(result["simulation_verified"])
        self.assertEqual(result["spent_base_units"],35)
        self.assertEqual(result["received_base_units"],24)
        self.assertEqual(result["min_output_base_units"],20)
        self.assertTrue(call.call_args.args[2][1]["sigVerify"])
        decode.side_effect=[
            {"mint":"base-mint","amount_base_units":65},
            {"mint":"quote-mint","amount_base_units":19}]
        with self.assertRaisesRegex(ValueError,"output threshold"):
            simulate_signed("http://127.0.0.1:8899",b"signed",
                "user-base","user-quote","base-mint","quote-mint",100,0,50,
                min_amount_out=20)

    def test_minimum_output_input_validation_fails_before_rpc(self):
        with patch("arb.pumpswap_local_simulation.call") as rpc:
            for bad in (0,-1,False,1<<64):
                with self.subTest(bad=bad):
                    with self.assertRaisesRegex(ValueError,"invalid signed"):
                        simulate_signed("http://127.0.0.1:8899",b"signed",
                            "user-base","user-quote","base-mint","quote-mint",
                            100,0,50,min_amount_out=bad)
            rpc.assert_not_called()

    @patch("arb.pumpswap_local_simulation.call")
    def test_reject_missing_post_state(self,call):
        from arb.pumpswap_pool import PROGRAM
        call.return_value={"value":{"err":None,
            "logs":["Program "+PROGRAM+" invoke [1]"],"accounts":[]}}
        with self.assertRaisesRegex(ValueError,"post-state"):
            simulate_signed("http://localhost:8899",b"signed",
                "user-base","user-quote","base-mint","quote-mint",100,0,50)
