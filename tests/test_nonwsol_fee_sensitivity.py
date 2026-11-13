import unittest
from unittest.mock import patch
from arb.m5_three_venue_observed_economics import evaluate
class Tests(unittest.TestCase):
    @patch("arb.m5_three_venue_observed_economics.accept",return_value=True)
    def test_non_wsol_exact_integer_fee_sensitivity_is_not_authenticated(self,_):
        f={"route_mints":["USDC","B","C","USDC"]}
        r={"planned_inputs":[100,80,60],
           "initial_balances_base_units":[100,0,0,0],
           "positive_post_balances_base_units":[0,0,0,120],
           "signed_message_fee_estimate":{"status":"SIGNED_MESSAGE_FEE_ESTIMATE_ONLY",
               "estimated_fee_lamports":5000,"signed_message_sha256":"test"}}
        out=evaluate(f,r,start_mint_base_units_per_sol=1000000,
                     conversion_authenticated=True)
        self.assertEqual(out["external_fx_fee_sensitivity"]
            ["estimated_network_fee_in_start_mint_units"],5)
        self.assertEqual(out["external_fx_fee_sensitivity"]
            ["gross_profit_less_estimated_separate_sol_fee_start_mint_units"],15)
        self.assertFalse(out["external_fx_fee_sensitivity"]
            ["conversion_independently_authenticated"])
        self.assertIsNone(out["net_delta_start_mint_base_units"])
        self.assertFalse(out["fee_source_verified"])
if __name__=="__main__":unittest.main()
