import unittest
from unittest.mock import patch
from arb.m5_three_venue_observed_economics import evaluate
W="So11111111111111111111111111111111111111112"
class Tests(unittest.TestCase):
    @patch("arb.m5_three_venue_observed_economics.accept",return_value=True)
    def test_sol_fee_payer_separate_from_unmodified_signed_swap_output(self,_):
        fixture={"route_mints":[W,"B","C",W]}
        receipt={"planned_inputs":[100,80,60],"initial_balances_base_units":[100,0,0,0],
          "positive_post_balances_base_units":[0,0,0,120],
          "signed_message_fee_estimate":{"status":"SIGNED_MESSAGE_FEE_ESTIMATE_ONLY",
          "estimated_fee_lamports":7,"signed_message_sha256":"message"}}
        x=evaluate(fixture,receipt)
        self.assertEqual(x["gross_output_base_units"],120)
        self.assertEqual(x["gross_delta_start_mint_base_units"],20)
        self.assertEqual(x["network_fee_payer_asset"],"SOL")
        self.assertFalse(x["network_fee_charged_to_swap_output"])
        self.assertEqual(x["swap_output_network_fee_deduction_base_units"],0)
        self.assertEqual(x["estimated_economic_surplus_after_separate_sol_fee_wsol_base_units"],13)
        self.assertIsNone(x["net_delta_start_mint_base_units"])
if __name__=="__main__":unittest.main()
