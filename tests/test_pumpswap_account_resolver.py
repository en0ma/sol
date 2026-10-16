import unittest
from unittest.mock import patch
from arb.pumpswap_account_resolver import resolve


class PumpSwapResolverTests(unittest.TestCase):
    def pool(self):
        return {"verified":True,"canonical_pool_verified":True,
                "address":"pool","base_mint":"base","quote_mint":"quote",
                "base_vault":"base_vault","quote_vault":"quote_vault",
                "coin_creator":"creator"}

    def test_unverified_pool_fails_before_derivation(self):
        pool=self.pool()
        pool["verified"]=False
        with self.assertRaisesRegex(ValueError,"verified pool"):
            resolve(pool,"user","userbase","userquote","recipient")
        pool=self.pool()
        pool["canonical_pool_verified"]=False
        with self.assertRaisesRegex(ValueError,"verified pool creator"):
            resolve(pool,"user","userbase","userquote","recipient")

    def test_unsupported_quote_token_program_fails(self):
        from arb.pumpswap_account_resolver import TOKEN_PROGRAM
        with self.assertRaisesRegex(ValueError,"classic SPL"):
            resolve(self.pool(),"user","userbase","userquote","recipient",
                    quote_token_program="some-other-program")
