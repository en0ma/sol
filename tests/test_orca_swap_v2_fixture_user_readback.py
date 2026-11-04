import base64
import unittest
from unittest.mock import patch
from solders.pubkey import Pubkey
from arb.orca_swap_v2_fixture_user_readback import observe_fixture_user_accounts
from arb.orca_swap_v2_local_token_accounts import TOKEN_PROGRAMS

TOKEN = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN22 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
A = "So11111111111111111111111111111111111111112"
B = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
AUTH = "11111111111111111111111111111111"

def plan():
    return {"status": "USER_ACCOUNT_BINDING_PLAN_ONLY", "pool_snapshot_slot": 100,
            "required_accounts": [
                {"role": "token_owner_account_a", "mint": A, "token_program": TOKEN22},
                {"role": "token_owner_account_b", "mint": B, "token_program": TOKEN}]}

def account(mint, program, authority=AUTH):
    raw = bytearray(165)
    raw[:32] = bytes(Pubkey.from_string(mint))
    raw[32:64] = bytes(Pubkey.from_string(authority))
    raw[108] = 1
    return {"owner": program, "executable": False,
            "data": [base64.b64encode(raw).decode(), "base64"]}

class FixtureUserReadbackTests(unittest.TestCase):
    def test_synchronized_observations_are_non_authorizing(self):
        response = {"context": {"slot": 101}, "value": [account(A, TOKEN22), account(B, TOKEN)]}
        with patch("arb.orca_swap_v2_fixture_user_readback.call", return_value=response) as rpc:
            result = observe_fixture_user_accounts("http://127.0.0.1:8899", plan(), [A, B], AUTH)
        self.assertEqual(rpc.call_args.args[1], "getMultipleAccounts")
        self.assertEqual(rpc.call_args.args[2][1]["minContextSlot"], 100)
        self.assertTrue(result["same_context_user_accounts_verified"])
        self.assertFalse(result["signer_control_verified"])
        self.assertFalse(result["signed_simulation_verified"])
        self.assertFalse(result["broadcast"])

    def test_wrong_mint_and_stale_slot_rejected(self):
        for response in (
            {"context": {"slot": 101}, "value": [account(B, TOKEN22), account(B, TOKEN)]},
            {"context": {"slot": 99}, "value": [account(A, TOKEN22), account(B, TOKEN)]},
            {"context": {"slot": 101}, "value": [None, account(B, TOKEN)]}
        ):
            with self.subTest(response=response["context"]), patch(
                "arb.orca_swap_v2_fixture_user_readback.call", return_value=response
            ), self.assertRaises(ValueError):
                observe_fixture_user_accounts("http://127.0.0.1:8899", plan(), [A, B], AUTH)

    def test_nonloopback_rejected(self):
        with self.assertRaises(ValueError):
            observe_fixture_user_accounts("https://api.mainnet-beta.solana.com", plan(), [A, B], AUTH)
