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

    @patch("arb.pumpswap_local_simulation.call")
    def test_reject_missing_post_state(self,call):
        from arb.pumpswap_pool import PROGRAM
        call.return_value={"value":{"err":None,
            "logs":["Program "+PROGRAM+" invoke [1]"],"accounts":[]}}
        with self.assertRaisesRegex(ValueError,"post-state"):
            simulate_signed("http://localhost:8899",b"signed",
                "user-base","user-quote","base-mint","quote-mint",100,0,50)
