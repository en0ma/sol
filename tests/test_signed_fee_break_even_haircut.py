import unittest
from unittest.mock import patch
from arb.m5_three_venue_observed_economics import evaluate
W="So11111111111111111111111111111111111111112"
class Tests(unittest.TestCase):
    @patch("arb.m5_three_venue_observed_economics.accept",return_value=True)
    def test_integer_break_even_haircut_with_exact_message_fee(self,_):
        f={"route_mints":[W,"B","C",W]}
        r={"planned_inputs":[100,80,60],
           "initial_balances_base_units":[100,0,0,0],
           "positive_post_balances_base_units":[0,0,0,120],
           "signed_message_fee_estimate":{"status":"SIGNED_MESSAGE_FEE_ESTIMATE_ONLY",
                  "estimated_fee_lamports":8,"signed_message_sha256":"test"}}
        report=evaluate(f,r)
        self.assertEqual(report["estimated_fee_break_even_output_base_units"],108)
        self.assertEqual(report["estimated_maximum_additional_output_haircut_bps"],1000)
        r["signed_message_fee_estimate"]["estimated_fee_lamports"]=25
        report=evaluate(f,r)
        self.assertIsNone(report["estimated_maximum_additional_output_haircut_bps"])
        self.assertEqual(report["estimated_net_delta_wsol_base_units"],-5)
        self.assertFalse(report["profitability_verified"])
if __name__=="__main__":unittest.main()
