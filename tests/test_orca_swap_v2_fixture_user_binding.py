import unittest
from arb.orca_swap_v2_fixture_user_binding import verify_fixture_user_observations

TOKEN = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN22 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

def case():
    plan = {"status": "USER_ACCOUNT_BINDING_PLAN_ONLY", "pool_snapshot_slot": 100,
            "required_accounts": [
                {"role": "token_owner_account_a", "mint": "mint-a", "token_program": TOKEN22},
                {"role": "token_owner_account_b", "mint": "mint-b", "token_program": TOKEN},
            ]}
    a = {"account": "a", "mint": "mint-a", "token_program": TOKEN22, "authority": "signer",
         "initialized": True, "local_rpc_verified": True, "slot": 101}
    b = {"account": "b", "mint": "mint-b", "token_program": TOKEN, "authority": "signer",
         "initialized": True, "local_rpc_verified": True, "slot": 101}
    return plan, a, b

class FixtureUserBindingTests(unittest.TestCase):
    def test_two_mint_programs_match_without_signer_claim(self):
        p, a, b = case()
        result = verify_fixture_user_observations(p, a, b, "signer")
        self.assertEqual(result["status"], "FIXTURE_USER_ACCOUNTS_READBACK_VERIFIED")
        self.assertFalse(result["same_atomic_pool_user_snapshot_verified"])
        self.assertFalse(result["signer_control_verified"])
        self.assertFalse(result["broadcast"])

    def test_mismatch_cases_fail_closed(self):
        for field, value in (("mint", "wrong"), ("token_program", TOKEN22),
                             ("authority", "other"), ("local_rpc_verified", False),
                             ("initialized", False), ("slot", 99), ("account", "")):
            p, a, b = case()
            b[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify_fixture_user_observations(p, a, b, "signer")

    def test_duplicate_accounts_and_divergent_slots_fail(self):
        p, a, b = case()
        b["account"] = "a"
        with self.assertRaises(ValueError):
            verify_fixture_user_observations(p, a, b, "signer")
        p, a, b = case()
        b["slot"] = 102
        with self.assertRaises(ValueError):
            verify_fixture_user_observations(p, a, b, "signer")
