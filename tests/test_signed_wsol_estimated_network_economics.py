import unittest
from unittest.mock import patch
from arb.m5_three_venue_observed_economics import evaluate
W="So11111111111111111111111111111111111111112"
class Tests(unittest.TestCase):
    @patch("arb.m5_three_venue_observed_economics.accept",return_value=True)
    def test_real_signed_message_quote_yields_estimated_wsol_net_not_paid_fee(self,_):
        fixture={"route_mints":[W,"B","C",W]}
        receipt={"planned_inputs":[100,80,60],
           "initial_balances_base_units":[100,0,0,0],
           "positive_post_balances_base_units":[0,0,0,120],
           "signed_message_fee_estimate":{"status":"SIGNED_MESSAGE_FEE_ESTIMATE_ONLY",
                 "signed_message_sha256":"signed-id","estimated_fee_lamports":7}}
        r=evaluate(fixture,receipt)
        self.assertEqual(r["estimated_net_delta_wsol_base_units"],13)
        self.assertEqual(r["estimated_fee_downside_scenarios"][0]["estimated_net_delta_wsol_base_units"],13)
        self.assertIsNone(r["net_delta_start_mint_base_units"])
        self.assertEqual(r["status"],"COST_EVIDENCE_BLOCKED")
        self.assertFalse(r["estimated_cost_is_paid_fee"])
        self.assertFalse(r["profitability_verified"])
    @patch("arb.m5_three_venue_observed_economics.accept",return_value=True)
    def test_non_wsol_rejects_unproven_conversion(self,_):
        fixture={"route_mints":["A","B","C","A"]}
        receipt={"planned_inputs":[100,80,60],
           "initial_balances_base_units":[100,0,0,0],
           "positive_post_balances_base_units":[0,0,0,120],
           "signed_message_fee_estimate":{"status":"SIGNED_MESSAGE_FEE_ESTIMATE_ONLY",
                 "signed_message_sha256":"signed-id","estimated_fee_lamports":7}}
        r=evaluate(fixture,receipt)
        self.assertNotIn("estimated_net_delta_wsol_base_units",r)
if __name__=="__main__":unittest.main()
