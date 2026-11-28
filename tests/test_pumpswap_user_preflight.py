import unittest
from unittest.mock import patch
from arb.pumpswap_user_preflight import verify_user_accounts


class PumpSwapUserPreflightTests(unittest.TestCase):
    def test_remote_rpc_rejected(self):
        with self.assertRaisesRegex(ValueError,"localhost"):
            verify_user_accounts("https://api.mainnet-beta.solana.com",
                "user","in","out","mint-in","mint-out",100,0)

    @patch("arb.pumpswap_user_preflight.call")
    def test_absent_user_accounts_rejected(self,call):
        call.return_value={"context":{"slot":1},"value":[None,None]}
        with self.assertRaisesRegex(ValueError,"missing or wrong program"):
            verify_user_accounts("http://127.0.0.1:8899",
                "user","in","out","mint-in","mint-out",100,0)
        self.assertEqual(call.call_args.args[1],"getMultipleAccounts")
        self.assertEqual(call.call_args.args[2][0],["in","out"])

    @patch("arb.pumpswap_user_preflight.call")
    def test_incomplete_snapshot_rejected(self,call):
        call.return_value={"context":{"slot":1},"value":[None]}
        with self.assertRaisesRegex(ValueError,"incomplete"):
            verify_user_accounts("http://127.0.0.1:8899",
                "user","in","out","mint-in","mint-out",100,0)

    def test_invalid_balance_rejected_before_network(self):
        with self.assertRaisesRegex(ValueError,"invalid"):
            verify_user_accounts("http://127.0.0.1:8899",
                "user","in","out","mint-in","mint-out",True,0)
