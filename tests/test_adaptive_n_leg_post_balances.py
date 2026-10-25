import unittest
from unittest.mock import patch
from arb.atomic_graph_coordinator import signed_n_leg_post_balances
class Tests(unittest.TestCase):
    def test_missing_signed_accounts_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"inventory missing"):
            signed_n_leg_post_balances({"accounts":[None]},["one","two"],["mint1","mint2"],"owner")
    def test_mismatched_authority_fails_closed(self):
        with patch("arb.token_vaults.decode_token_account",return_value={
            "mint":"mintA","authority":"other","amount_base_units":0}):
            with self.assertRaisesRegex(ValueError,"mint/authority mismatch"):
                signed_n_leg_post_balances({"accounts":[{"owner":"TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA","data":["YQ==","base64"]}]},
                     ["a"],["mintA"],"owner")
if __name__=="__main__":unittest.main()
