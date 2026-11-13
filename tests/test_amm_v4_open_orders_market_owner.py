"""Regression: Serum/OpenBook OpenOrders is owned by MARKET program, not AMM."""
import base64
import unittest
from unittest.mock import patch
from arb.raydium_amm_v4_preflight import verify_pool_market,PROGRAM
from arb.token_vaults import TOKEN_PROGRAM
from arb.raydium_amm_v4 import decode

class AmmV4MarketOwnerTests(unittest.TestCase):
    @patch("arb.raydium_amm_v4_preflight.decode")
    @patch("arb.raydium_amm_v4_preflight.decode_token_account")
    @patch("arb.raydium_amm_v4_preflight.call")
    def test_open_orders_owned_by_market_program_is_accepted(self,call,token,decode_pool):
        state={"base_vault":"base-v","quote_vault":"quote-v",
               "open_orders":"oo","market_id":"market","base_mint":"base",
               "quote_mint":"quote","market_program":"serum"}
        decode_pool.return_value=state
        token.side_effect=[{"mint":"base","amount_base_units":1},{"mint":"quote","amount_base_units":1}]
        def account(owner):
            return {"owner":owner,"executable":False,
                    "data":[base64.b64encode(b"abc").decode(),"base64"]}
        call.return_value={"context":{"slot":123},"value":[account(PROGRAM),
            account(TOKEN_PROGRAM),account(TOKEN_PROGRAM),
            account("serum"),account("serum")]}
        evidence=verify_pool_market("http://127.0.0.1:8899","pool",state)
        self.assertTrue(evidence["pool_and_market_authenticated"])
        self.assertFalse(evidence["market_accounts_authenticated"])
    @patch("arb.raydium_amm_v4_preflight.decode")
    @patch("arb.raydium_amm_v4_preflight.decode_token_account")
    @patch("arb.raydium_amm_v4_preflight.call")
    def test_amm_owned_open_orders_rejected(self,call,token,decode_pool):
        state={"base_vault":"base-v","quote_vault":"quote-v",
               "open_orders":"oo","market_id":"market","base_mint":"base",
               "quote_mint":"quote","market_program":"serum"}
        decode_pool.return_value=state
        token.side_effect=[{"mint":"base","amount_base_units":1},{"mint":"quote","amount_base_units":1}]
        def account(owner):
            return {"owner":owner,"executable":False,
                    "data":[base64.b64encode(b"abc").decode(),"base64"]}
        call.return_value={"context":{"slot":123},"value":[account(PROGRAM),
            account(TOKEN_PROGRAM),account(TOKEN_PROGRAM),
            account(PROGRAM),account("serum")]}
        with self.assertRaisesRegex(ValueError,"both"):
            verify_pool_market("http://127.0.0.1:8899","pool",state)

if __name__=="__main__":unittest.main()
