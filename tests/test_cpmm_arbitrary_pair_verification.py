import unittest
from unittest.mock import patch
from arb.raydium_cpmm import verify_vaults
from arb.orca_whirlpool import SOL, USDC

RAY="4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"

class ArbitraryCpmmPairTests(unittest.TestCase):
    def test_default_stays_sol_usdc_fail_closed(self):
        state={"token_0_mint": SOL,"token_1_mint": RAY}
        with self.assertRaisesRegex(ValueError,"unexpected CPMM token pair"):
            verify_vaults("http://127.0.0.1:8899","pool",state)

    @patch("arb.raydium_cpmm.decode_token_account")
    @patch("arb.raydium_cpmm.decode")
    @patch("arb.raydium_cpmm.call")
    def test_other_pair_vault_verification_requires_matching_onchain_state(self, call, decode, token):
        from arb.raydium_cpmm import PROGRAM
        from arb.token_vaults import TOKEN_PROGRAM
        state={"token_0_mint":SOL,"token_1_mint":RAY,
               "token_0_program":TOKEN_PROGRAM,"token_1_program":TOKEN_PROGRAM,
               "token_0_vault":"vault0","token_1_vault":"vault1",
               "swap_enabled":True}
        call.return_value={"context":{"slot":50},"value":[
            {"owner":PROGRAM,"data":["AA==","base64"]},
            {"owner":TOKEN_PROGRAM,"data":["AA==","base64"]},
            {"owner":TOKEN_PROGRAM,"data":["AA==","base64"]}]}
        decode.return_value=state
        token.side_effect=[
            {"mint":SOL,"amount_base_units":100,"authority":"same"},
            {"mint":RAY,"amount_base_units":100,"authority":"same"}]
        out=verify_vaults("http://127.0.0.1:8899","pool",state,expected_mints=None)
        self.assertTrue(out["verified"])
        self.assertEqual(out["reserves_base_units"],[100,100])

    def test_duplicate_mints_fail_even_in_graph_mode(self):
        with self.assertRaisesRegex(ValueError,"identical CPMM"):
            verify_vaults("http://127.0.0.1:8899","pool",
                          {"token_0_mint":RAY,"token_1_mint":RAY},expected_mints=None)
