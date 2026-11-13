"""Signed PumpSwap instruction-intent checks, not synthetic execution receipts."""
import unittest

from arb.pumpswap_signed_parity import verify_transaction_intent
from arb.pumpswap_trade_v2 import build_v2,ORDER
from arb.pumpswap_pool import PROGRAM
from arb.pumpswap_account_resolver import SYSTEM
from arb.token_vaults import TOKEN_PROGRAM


class PumpSwapSignedInstructionBindingTest(unittest.TestCase):
    def signed(self):
        from solders.keypair import Keypair
        from solders.transaction import Transaction,VersionedTransaction
        from solders.hash import Hash
        user=Keypair()
        roles={key:str(Keypair().pubkey()) for key in ORDER}
        roles.update({"user":str(user.pubkey()),"program":PROGRAM,
            "system_program":SYSTEM,"base_token_program":TOKEN_PROGRAM,
            "quote_token_program":TOKEN_PROGRAM,
            "buyback_fee_recipient_authenticated":True})
        ix=build_v2("sell",roles,10000,200)
        tx=Transaction.new_signed_with_payer([ix],user.pubkey(),[user],
            Hash.from_string(SYSTEM))
        return VersionedTransaction.from_bytes(bytes(tx)),roles

    def test_signed_swap_intent_matches_exact_v2(self):
        tx,roles=self.signed()
        verify_transaction_intent(tx,roles["pool"],roles["base_mint"],
            roles["quote_mint"],roles["user_base_token_account"],
            roles["user_quote_token_account"],10000,200)

    def test_wrong_pool_cannot_impersonate_signed_receipt(self):
        from solders.keypair import Keypair
        tx,roles=self.signed()
        with self.assertRaisesRegex(ValueError,"pool or mint mismatch"):
            verify_transaction_intent(tx,str(Keypair().pubkey()),
                roles["base_mint"],roles["quote_mint"],
                roles["user_base_token_account"],
                roles["user_quote_token_account"],10000,200)

    def test_wrong_amount_cannot_impersonate_signed_receipt(self):
        tx,roles=self.signed()
        with self.assertRaisesRegex(ValueError,"amount or minimum mismatch"):
            verify_transaction_intent(tx,roles["pool"],roles["base_mint"],
                roles["quote_mint"],roles["user_base_token_account"],
                roles["user_quote_token_account"],10001,200)

    def test_wrong_input_account_cannot_impersonate_receipt(self):
        from solders.keypair import Keypair
        tx,roles=self.signed()
        with self.assertRaisesRegex(ValueError,"token account roles"):
            verify_transaction_intent(tx,roles["pool"],roles["base_mint"],
                roles["quote_mint"],str(Keypair().pubkey()),
                roles["user_quote_token_account"],10000,200)


if __name__=="__main__":
    unittest.main()
