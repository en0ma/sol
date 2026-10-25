import unittest
from unittest.mock import patch
from arb.m5_three_venue_observed_economics import evaluate
class Tests(unittest.TestCase):
    def source(self):return {}
    def receipt(self):return {"planned_inputs":[100,90,80],
        "initial_balances_base_units":[100,0,0,0],
        "positive_post_balances_base_units":[0,0,0,120]}
    @patch("arb.m5_three_venue_observed_economics.accept",return_value={})
    def test_missing_fee_or_conversion_is_blocked(self,_):
        for options in ({},{"observed_fee_lamports":5000},
                        {"observed_fee_lamports":5000,"start_mint_base_units_per_sol":1000000}):
            report=evaluate(self.source(),self.receipt(),**options)
            self.assertEqual(report["status"],"COST_EVIDENCE_BLOCKED")
            self.assertIsNone(report["net_delta_start_mint_base_units"])
    @patch("arb.m5_three_venue_observed_economics.accept",return_value={})
    def test_observed_inputs_and_downside_exact_integer_math(self,_):
        r=evaluate(self.source(),self.receipt(),observed_fee_lamports=5000,
                   start_mint_base_units_per_sol=1_000_000,conversion_authenticated=True)
        self.assertEqual(r["fee_start_mint_base_units"],5)
        self.assertEqual(r["maximum_affordable_total_cost_start_mint_base_units"],20)
        self.assertEqual(r["gross_return_bps"],2000)
        self.assertEqual(r["net_delta_start_mint_base_units"],15)
        self.assertEqual(r["downside_scenarios"][0]["net_delta_start_mint_base_units"],15)
        self.assertFalse(r["profitability_verified"])
        self.assertFalse(r["broadcast"])
    @patch("arb.m5_three_venue_observed_economics.accept",side_effect=ValueError("fake"))
    def test_unaccepted_signed_receipt_blocks(self,_):
        self.assertEqual(evaluate({},self.receipt())["status"],"COST_EVIDENCE_BLOCKED")
if __name__=="__main__":unittest.main()
