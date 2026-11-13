import unittest
from unittest.mock import patch
from arb.m5_three_venue_observed_economics import evaluate
class Tests(unittest.TestCase):
    @patch("arb.m5_three_venue_observed_economics.accept",return_value=True)
    def test_non_wsol_keeps_two_asset_accounting_without_guessing_sol_price(self,_):
        f={"route_mints":["USDC","B","C","USDC"]}
        r={"planned_inputs":[100,80,60],
           "initial_balances_base_units":[100,0,0,0],
           "positive_post_balances_base_units":[0,0,0,120],
           "signed_message_fee_estimate":{"status":"SIGNED_MESSAGE_FEE_ESTIMATE_ONLY",
             "signed_message_sha256":"signed","estimated_fee_lamports":5000}}
        out=evaluate(f,r)
        ledger=out["economic_asset_ledger"]
        self.assertEqual(ledger["swap_output"],{"mint":"USDC","base_units":120})
        self.assertEqual(ledger["gross_trade_profit"],{"mint":"USDC","base_units":20})
        self.assertEqual(ledger["network_fee"]["estimated_lamports"],5000)
        self.assertEqual(ledger["network_fee"]["mint"],"SOL")
        self.assertIsNone(ledger["network_fee"]["paid_lamports"])
        self.assertFalse(ledger["fee_payer_is_swap_output_account"])
        self.assertIsNone(out["net_delta_start_mint_base_units"])
if __name__=="__main__":unittest.main()
