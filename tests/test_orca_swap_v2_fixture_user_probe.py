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
             patch("arb.orca_swap_v2_fixture_user_probe.observe_fixture_user_accounts", side_effect=ValueError("no account")):
            result = run(RPC, account_a="a", account_b="b", authority="c")
        self.assertEqual(result["status"], "FIXTURE_USER_ACCOUNTS_NOT_VERIFIED")
        self.assertFalse(result["signed_simulation_verified"])

    def test_nonloopback_rejected(self):
        with self.assertRaises(ValueError):
            run("https://api.mainnet-beta.solana.com")
