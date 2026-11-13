import unittest
from unittest.mock import patch

from arb.damm_v2_fork_execution import execute, provision_offline_user, SAFETY

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

    def test_ephemeral_provision_requires_explicit_offline_opt_in(self):
        with patch.dict("os.environ", {"SURFPOOL_EXPLICITLY_OFFLINE": "0"}):
            with patch("arb.damm_v2_fork_execution.call") as rpc:
                with self.assertRaisesRegex(ValueError, "explicit offline"):
                    provision_offline_user("http://localhost:8899",
                        pool="pool", input_is_a=True, amount_in=25)
                rpc.assert_not_called()

    def test_ephemeral_provision_rejects_remote_rpc(self):
        with patch("arb.damm_v2_fork_execution.call") as rpc:
            with self.assertRaises(ValueError):
                provision_offline_user("https://api.mainnet-beta.solana.com",
                    pool="pool", input_is_a=True, amount_in=25)
            rpc.assert_not_called()

    def test_ephemeral_provision_fails_before_cheatcode_on_wrong_pool(self):
        with patch.dict("os.environ", {"SURFPOOL_EXPLICITLY_OFFLINE": "1"}):
            with patch("arb.damm_v2_fork_execution.call",
                       return_value={"value": {"owner": "wrong", "executable": False}}) as rpc:
                with self.assertRaisesRegex(ValueError, "pool missing"):
                    provision_offline_user("http://localhost:8899",
                        pool="pool", input_is_a=True, amount_in=25)
                self.assertEqual(rpc.call_count, 1)
                self.assertEqual(rpc.call_args.args[1], "getAccountInfo")


    def test_negative_control_rejects_unrelated_runtime_failure(self):
        from arb.damm_v2_fork_execution import _signed_negative_control
        from solders.hash import Hash
        with patch("arb.damm_v2_fork_execution.build_swap2") as builder:
            from solders.instruction import Instruction
            from solders.pubkey import Pubkey
            from arb.meteora_damm_v2 import PROGRAM
            builder.return_value = Instruction(Pubkey.from_string(PROGRAM), b"swap", [])
            with patch("arb.rpc.call", side_effect=[
                    {"value": {"blockhash": str(Hash.default())}},
                    {"value": {"err": "BlockhashNotFound", "logs": []}}]):
                with self.assertRaisesRegex(ValueError, "does not establish"):
                    _signed_negative_control("http://localhost:8899", pool="pool",
                        state={}, signer=self.signer, input_account="input",
                        output_account="output", amount_in=25, input_is_a=True)

    def test_negative_proof_must_explicitly_be_true(self):
        with self.assertRaisesRegex(ValueError, "negative slippage"):
            self._execute(negative=False)

    def test_fails_closed_on_stale_pool_snapshot(self):
        with patch("arb.damm_v2_fork_execution.call",
                   return_value={"context": {"slot": 100}, "value": None}):
            with self.assertRaisesRegex(ValueError, "not authenticated"):
                execute("http://localhost:8899", **self.kwargs)


if __name__ == "__main__":
    unittest.main()
