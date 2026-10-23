import unittest
from unittest.mock import patch

from arb.damm_v2_fork_execution import execute, SAFETY

try:
    from solders.keypair import Keypair
    HAVE_SOLDERS = True
except ImportError:
    HAVE_SOLDERS = False


@unittest.skipUnless(HAVE_SOLDERS, "solders required for fork execution harness")
class DammV2ForkExecutionTests(unittest.TestCase):
    def setUp(self):
        self.signer = Keypair()
        self.state = {"token_a_mint": "A", "token_b_mint": "B"}
        self.kwargs = dict(pool="pool", signer=self.signer,
                           input_account="input", output_account="output",
                           amount_in=25, min_amount_out=2, input_is_a=True)

    def _execute(self, negative=True, signed=True):
        import base64
        with patch("arb.damm_v2_fork_execution.call",
                   return_value={"context": {"slot": 100},
                                 "value": {"owner": "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG",
                                           "executable": False,
                                           "data": [base64.b64encode(b"raw").decode(), "base64"]}}):
            with patch("arb.damm_v2_fork_execution.decode", return_value=self.state):
                with patch("arb.damm_v2_fork_execution.verify",
                           return_value={"slot": 101, "venue": "meteora_damm_v2"}):
                    with patch("arb.damm_v2_fork_execution._account_snapshot",
                               return_value=(101, [100, 0])):
                        with patch("arb.damm_v2_fork_execution.verify_user_accounts"):
                            with patch("arb.damm_v2_fork_execution.sign_and_simulate",
                                       return_value={"signed_standalone_simulation_verified": signed,
                                                     "transaction_signature": "signed",
                                                     "pool": "pool"}) as runner:
                                with patch("arb.damm_v2_fork_execution._signed_negative_control",
                                           return_value={"negative_slippage_failure_observed": negative}) as neg:
                                    result = execute("http://127.0.0.1:8899", **self.kwargs)
                                    return result, runner, neg

    def test_harness_retains_success_and_negative_case_without_broadcast(self):
        result, runner, neg = self._execute()
        self.assertTrue(result["positive_and_negative_controls_verified"])
        self.assertTrue(result["signed_standalone_simulation_verified"])
        self.assertEqual(result["user_snapshot_slot"], 101)
        self.assertEqual(runner.call_args.kwargs["amount_in"], 25)
        self.assertEqual(runner.call_args.kwargs["min_amount_out"], 2)
        neg.assert_called_once()
        for key, value in SAFETY.items():
            self.assertIs(result[key], value)

    def test_no_negative_control_before_positive_proof(self):
        with self.assertRaisesRegex(ValueError, "positive standalone"):
            self._execute(signed=False)

    def test_rejects_remote_rpc_without_reading_accounts(self):
        with patch("arb.damm_v2_fork_execution.call") as rpc:
            with self.assertRaises(ValueError):
                execute("https://api.mainnet-beta.solana.com", **self.kwargs)
            rpc.assert_not_called()

    def test_rejects_invalid_input_before_rpc(self):
        kwargs = {**self.kwargs, "amount_in": 0}
        with patch("arb.damm_v2_fork_execution.call") as rpc:
            with self.assertRaises(ValueError):
                execute("http://localhost:8899", **kwargs)
            rpc.assert_not_called()

    def test_fails_closed_on_stale_pool_snapshot(self):
        with patch("arb.damm_v2_fork_execution.call",
                   return_value={"context": {"slot": 100}, "value": None}):
            with self.assertRaisesRegex(ValueError, "not authenticated"):
                execute("http://localhost:8899", **self.kwargs)


if __name__ == "__main__":
    unittest.main()
