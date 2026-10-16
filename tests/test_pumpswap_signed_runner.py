import unittest
from unittest.mock import patch
from arb.pumpswap_signed_runner import sign_and_simulate


class Payer:
    def pubkey(self): return "user"


class PumpSwapSignedRunnerTests(unittest.TestCase):
    def pool(self):
        return {"verified":True,"canonical_pool_verified":True,"address":"pool",
                "base_mint":"base","quote_mint":"quote"}

    def test_external_rpc_denied_before_signing(self):
        with self.assertRaisesRegex(ValueError,"localhost"):
            sign_and_simulate("https://api.mainnet-beta.solana.com",
                self.pool(),Payer(),"sell",{},100,1,"base-account","quote-account",100,0)

    def test_wrong_payer_or_pool_denied(self):
        with self.assertRaisesRegex(ValueError,"identity mismatch"):
            sign_and_simulate("http://127.0.0.1:8899",self.pool(),Payer(),"sell",
                {"user":"someone-else","pool":"pool"},100,1,
                "base-account","quote-account",100,0)

    def test_inverted_token_addresses_denied(self):
        with self.assertRaisesRegex(ValueError,"direction mismatch"):
            sign_and_simulate("http://127.0.0.1:8899",self.pool(),Payer(),"sell",
                {"user":"user","pool":"pool",
                 "user_base_token_account":"base-account",
                 "user_quote_token_account":"quote-account"},100,1,
                "quote-account","base-account",100,0)
