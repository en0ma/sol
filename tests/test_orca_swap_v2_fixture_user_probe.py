import unittest
from unittest.mock import patch
from arb.orca_swap_v2_fixture_user_probe import run

RPC = "http://127.0.0.1:8899"

class FixtureUserProbeTests(unittest.TestCase):
    def test_missing_addresses_report_blocked_without_rpc_calls(self):
        with patch("arb.orca_swap_v2_fixture_user_probe.snapshot") as snapshot:
            result = run(RPC)
        snapshot.assert_not_called()
        self.assertEqual(result["status"], "FIXTURE_USER_ACCOUNTS_NOT_CONFIGURED")
        self.assertFalse(result["user_token_accounts_verified"])
        self.assertFalse(result["broadcast"])

    def test_readback_failure_stays_nonactionable(self):
        with patch("arb.orca_swap_v2_fixture_user_probe.snapshot", return_value={"structurally_verified": True}), \
             patch("arb.orca_swap_v2_fixture_user_probe.plan_user_account_binding", return_value={"status":"USER_ACCOUNT_BINDING_PLAN_ONLY"}), \
             patch("arb.orca_swap_v2_fixture_user_probe.observe_atomic_pool_user_identities", side_effect=ValueError("no account")):
            result = run(RPC, account_a="a", account_b="b", authority="c")
        self.assertEqual(result["status"], "FIXTURE_USER_ACCOUNTS_NOT_VERIFIED")
        self.assertFalse(result["signed_simulation_verified"])

    def test_configured_input_funding_is_diagnostic_only(self):
        observations = {"status": "SAME_CONTEXT_POOL_USER_IDENTITIES_VERIFIED",
                        "observed_balances_base_units": [100, 50],
                        "observation_slot": 12,
                        "signed_simulation_verified": False, "broadcast": False}
        with patch("arb.orca_swap_v2_fixture_user_probe.snapshot", return_value={"structurally_verified": True}), \
             patch("arb.orca_swap_v2_fixture_user_probe.plan_user_account_binding", return_value={"status": "USER_ACCOUNT_BINDING_PLAN_ONLY"}), \
             patch("arb.orca_swap_v2_fixture_user_probe.observe_atomic_pool_user_identities", side_effect=lambda *args: observations.copy()):
            funded = run(RPC, account_a="a", account_b="b", authority="c",
                         a_to_b=True, required_amount=80)
            lacking = run(RPC, account_a="a", account_b="b", authority="c",
                          a_to_b=False, required_amount=80)
            with self.assertRaises(ValueError):
                run(RPC, account_a="a", account_b="b", authority="c",
                    a_to_b=True)
        self.assertEqual(funded["funding_check_status"], "INPUT_FUNDING_OBSERVED")
        self.assertEqual(lacking["funding_check_status"], "INPUT_FUNDING_INSUFFICIENT")
        self.assertFalse(funded["funding_check"]["signed_simulation_verified"])
        self.assertFalse(funded["broadcast"])

    def test_nonloopback_rejected(self):
        with self.assertRaises(ValueError):
            run("https://api.mainnet-beta.solana.com")
