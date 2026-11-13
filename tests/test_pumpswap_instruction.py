import unittest
from arb.pumpswap_instruction import build_instruction
from arb.pumpswap_account_metas import SELL,BUY_EXACT_QUOTE_IN


class PumpSwapInstructionTests(unittest.TestCase):
    def accounts(self,names):
        value={name:"address-"+str(i) for i,name in enumerate(names)}
        value["program"]="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
        value["fee_program"]="pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ"
        return value

    def test_missing_accounts_rejected_before_dependency(self):
        with self.assertRaisesRegex(ValueError,"missing PumpSwap account"):
            build_instruction("sell",{},10,1)
        with self.assertRaisesRegex(ValueError,"missing PumpSwap account"):
            build_instruction("buy_exact_quote_in",{},10,1)

    def test_bad_slippage_rejected(self):
        with self.assertRaisesRegex(ValueError,"swap amount"):
            build_instruction("sell",self.accounts(SELL),100,0)
        with self.assertRaisesRegex(ValueError,"OptionBool"):
            build_instruction("buy_exact_quote_in",self.accounts(BUY_EXACT_QUOTE_IN),
                              100,1,track_volume="true")

    def test_sell_does_not_accept_volume_arg(self):
        with self.assertRaisesRegex(ValueError,"does not accept"):
            build_instruction("sell",self.accounts(SELL),100,1,track_volume=False)
