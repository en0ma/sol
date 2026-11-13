import os
import unittest
from unittest.mock import patch
from solders.keypair import Keypair
from arb.orca_swap_v2_fixture_offline_provision import provision_offline_fixture_accounts

TOKEN = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN22 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
MINT_A = "So11111111111111111111111111111111111111112"
MINT_B = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

def plan():
    return {"status": "USER_ACCOUNT_BINDING_PLAN_ONLY",
            "required_accounts": [
                {"role": "token_owner_account_a", "mint": MINT_A, "token_program": TOKEN22},
                {"role": "token_owner_account_b", "mint": MINT_B, "token_program": TOKEN}]}

class FixtureOfflineProvisionTests(unittest.TestCase):
    def test_mixed_token_programs_used_only_offline(self):
        with patch.dict(os.environ, {"SURFPOOL_EXPLICITLY_OFFLINE": "1"}), \
             patch("arb.orca_swap_v2_fixture_offline_provision.call", return_value={}) as rpc:
            report = provision_offline_fixture_accounts(
                "http://127.0.0.1:8899", plan(), Keypair(), amounts=(10, 0))
        self.assertEqual(rpc.call_count, 2)
        calls = rpc.call_args_list
        self.assertEqual(calls[0].args[2][1]["owner"], TOKEN22)
        self.assertEqual(calls[1].args[2][1]["owner"], TOKEN)
        self.assertEqual(report["amounts_base_units"], [10, 0])
        self.assertFalse(report["runtime_token_account_semantics_verified"])
        self.assertFalse(report["signed_simulation_verified"])
        self.assertFalse(report["broadcast"])

    def test_no_offline_optin_rejects_before_any_rpc(self):
        with patch.dict(os.environ, {"SURFPOOL_EXPLICITLY_OFFLINE": "0"}), \
             patch("arb.orca_swap_v2_fixture_offline_provision.call") as rpc:
            with self.assertRaises(ValueError):
                provision_offline_fixture_accounts("http://127.0.0.1:8899", plan(), Keypair())
            rpc.assert_not_called()

    def test_nonloopback_and_invalid_roles_rejected(self):
        with patch.dict(os.environ, {"SURFPOOL_EXPLICITLY_OFFLINE": "1"}):
            with self.assertRaises(ValueError):
                provision_offline_fixture_accounts("https://api.mainnet-beta.solana.com", plan(), Keypair())
            bad = plan()
            bad["required_accounts"][0]["role"] = "wrong"
            with self.assertRaises(ValueError):
                provision_offline_fixture_accounts("http://127.0.0.1:8899", bad, Keypair())
