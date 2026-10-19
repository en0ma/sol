import base64
import unittest
from unittest.mock import patch
from solders.pubkey import Pubkey
from arb.orca_swap_v2_atomic_pool_user_readback import observe_atomic_pool_user_identities
from arb.orca_whirlpool import PROGRAM

POOL = "94BpFoyri4uTT55NFSHKYNFyUMtoWXEisMA4LK7nTKPU"
VAULT_A = "SysvarRent111111111111111111111111111111111"
VAULT_B = "Stake11111111111111111111111111111111111111"
MINT_A = "So11111111111111111111111111111111111111112"
MINT_B = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
TOKEN = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN22 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
AUTH = "11111111111111111111111111111111"

def plan():
    return {"status": "USER_ACCOUNT_BINDING_PLAN_ONLY", "pool_address": POOL,
            "pool_snapshot_slot": 100, "pool_vault_addresses": [VAULT_A, VAULT_B], "required_accounts": [
                {"role": "token_owner_account_a", "mint": MINT_A, "token_program": TOKEN22},
                {"role": "token_owner_account_b", "mint": MINT_B, "token_program": TOKEN}]}

def data(raw, owner):
    return {"owner": owner, "executable": False,
            "data": [base64.b64encode(raw).decode(), "base64"]}

def token(mint, owner):
    raw = bytearray(165)
    raw[:32] = bytes(Pubkey.from_string(mint))
    raw[32:64] = bytes(Pubkey.from_string(AUTH))
    raw[108] = 1
    raw[64:72] = (10).to_bytes(8, "little")
    return data(raw, owner)

def response(slot=101):
    return {"context": {"slot": slot}, "value": [
        data(bytes(300), PROGRAM), token(MINT_A, TOKEN22), token(MINT_B, TOKEN),
        token(MINT_A, TOKEN22), token(MINT_B, TOKEN)]}

class AtomicPoolUserReadbackTests(unittest.TestCase):
    def test_single_rpc_context_binds_pool_and_both_accounts(self):
        with patch("arb.orca_swap_v2_atomic_pool_user_readback.call", return_value=response()) as call, \
             patch("arb.orca_swap_v2_atomic_pool_user_readback.decode",
                   return_value={"token_mint_a": MINT_A, "token_mint_b": MINT_B, "token_vault_a": VAULT_A, "token_vault_b": VAULT_B}):
            result = observe_atomic_pool_user_identities(
                "http://127.0.0.1:8899", plan(), [MINT_A, MINT_B], AUTH)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(call.call_args.args[2][0], [POOL, MINT_A, MINT_B, VAULT_A, VAULT_B])
        self.assertEqual(result["observed_balances_base_units"], [10, 10])
        self.assertTrue(result["same_context_pool_user_identities_verified"])
        self.assertTrue(result["same_context_vault_mint_programs_verified"])
        self.assertFalse(result["signer_control_verified"])
        self.assertFalse(result["signed_simulation_verified"])

    def test_pool_mint_mismatch_fails_closed(self):
        with patch("arb.orca_swap_v2_atomic_pool_user_readback.call", return_value=response()), \
             patch("arb.orca_swap_v2_atomic_pool_user_readback.decode",
                   return_value={"token_mint_a": MINT_B, "token_mint_b": MINT_A, "token_vault_a": VAULT_A, "token_vault_b": VAULT_B}):
            with self.assertRaises(ValueError):
                observe_atomic_pool_user_identities(
                    "http://127.0.0.1:8899", plan(), [MINT_A, MINT_B], AUTH)

    def test_changed_vault_identity_fails_closed(self):
        with patch("arb.orca_swap_v2_atomic_pool_user_readback.call", return_value=response()), \
             patch("arb.orca_swap_v2_atomic_pool_user_readback.decode",
                   return_value={"token_mint_a": MINT_A, "token_mint_b": MINT_B,
                                 "token_vault_a": VAULT_B, "token_vault_b": VAULT_A}):
            with self.assertRaisesRegex(ValueError, "vault identities changed"):
                observe_atomic_pool_user_identities(
                    "http://127.0.0.1:8899", plan(), [MINT_A, MINT_B], AUTH)

    def test_vault_mint_mismatch_rejected(self):
        invalid = response()
        invalid["value"][3] = token(MINT_B, TOKEN22)
        with patch("arb.orca_swap_v2_atomic_pool_user_readback.call", return_value=invalid), \
             patch("arb.orca_swap_v2_atomic_pool_user_readback.decode",
                   return_value={"token_mint_a": MINT_A, "token_mint_b": MINT_B,
                                 "token_vault_a": VAULT_A, "token_vault_b": VAULT_B}):
            with self.assertRaisesRegex(ValueError, "pool vault mint"):
                observe_atomic_pool_user_identities(
                    "http://127.0.0.1:8899", plan(), [MINT_A, MINT_B], AUTH)

    def test_stale_slot_and_invalid_rpc_fail(self):
        with patch("arb.orca_swap_v2_atomic_pool_user_readback.call", return_value=response(99)):
            with self.assertRaises(ValueError):
                observe_atomic_pool_user_identities(
                    "http://127.0.0.1:8899", plan(), [MINT_A, MINT_B], AUTH)
        with self.assertRaises(ValueError):
            observe_atomic_pool_user_identities(
                "https://api.mainnet-beta.solana.com", plan(), [MINT_A, MINT_B], AUTH)
