import unittest
from arb.pumpswap_account_metas import account_metas, SELL, BUY_EXACT_QUOTE_IN


class PumpSwapAccountMetaTests(unittest.TestCase):
    def addresses(self,names):
        result={name:"account-"+str(i) for i,name in enumerate(names)}
        result["program"]="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
        result["fee_program"]="pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ"
        return result

    def test_sell_order_and_signer(self):
        result=account_metas("sell",self.addresses(SELL))
        self.assertEqual([x["name"] for x in result["metas"]],SELL)
        self.assertEqual([x["name"] for x in result["metas"] if x["is_signer"]],["user"])
        self.assertFalse(result["transaction_built"])

    def test_buy_has_volume_accounts_before_fee_config(self):
        result=account_metas("buy_exact_quote_in",self.addresses(BUY_EXACT_QUOTE_IN))
        names=[x["name"] for x in result["metas"]]
        self.assertEqual(names[-4:],["global_volume_accumulator","user_volume_accumulator",
                                      "fee_config","fee_program"])
        self.assertTrue(result["metas"][-3]["is_writable"])

    def test_missing_wrong_program_and_duplicate_accounts_rejected(self):
        accounts=self.addresses(SELL)
        del accounts["coin_creator_vault_ata"]
        with self.assertRaisesRegex(ValueError,"missing"):
            account_metas("sell",accounts)
        accounts=self.addresses(SELL)
        accounts["program"]="wrong"
        with self.assertRaisesRegex(ValueError,"program mismatch"):
            account_metas("sell",accounts)
        accounts=self.addresses(SELL)
        accounts["user"]=accounts["pool"]
        with self.assertRaisesRegex(ValueError,"duplicate"):
            account_metas("sell",accounts)
