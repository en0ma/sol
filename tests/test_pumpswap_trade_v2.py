import hashlib
import unittest
from unittest.mock import patch
from arb.pumpswap_trade_v2 import build_v2,ORDER
from arb.pumpswap_pool import PROGRAM
from arb.pumpswap_global_config import authenticated_buyback_wallets,DISC
from arb.token_vaults import TOKEN_PROGRAM
from arb.pumpswap_account_resolver import SYSTEM

class PumpSwapV2IntegrationTests(unittest.TestCase):
    def test_missing_buyback_authentication_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"unauthenticated"):
            build_v2("sell",{"program":PROGRAM,"base_token_program":TOKEN_PROGRAM,
                     "quote_token_program":TOKEN_PROGRAM,"system_program":SYSTEM},100,1)
    def test_v2_exact_input_instruction_order_and_discriminator(self):
        from solders.pubkey import Pubkey
        addresses={key:str(Pubkey.new_unique()) for key in ORDER}
        addresses.update(program=PROGRAM,base_token_program=TOKEN_PROGRAM,
                         quote_token_program=TOKEN_PROGRAM,system_program=SYSTEM,
                         buyback_fee_recipient_authenticated=True)
        for direction,tag in (("sell","sell_v2"),("buy_exact_quote_in","buy_exact_quote_in_v2")):
            ix=build_v2(direction,addresses,123,1)
            self.assertEqual(len(ix.accounts),17)
            self.assertEqual(ix.data[:8],hashlib.sha256(("global:"+tag).encode()).digest()[:8])
            self.assertEqual(int.from_bytes(ix.data[8:16],"little"),123)
            self.assertTrue(ix.accounts[1].is_signer)
    def test_truncated_global_config_buyback_table_rejected(self):
        with self.assertRaisesRegex(ValueError,"table unavailable"):
            authenticated_buyback_wallets(DISC+bytes(321))
if __name__=="__main__":unittest.main()
