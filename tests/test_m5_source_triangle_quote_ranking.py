import unittest
from unittest.mock import patch
from arb.m5_source_triangle_quote_ranking import rank

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
FIXTURE={"route_venues":["orca","raydium_cpmm","raydium_amm_v4"],
         "route_mints":["A","B","C","A"],
         "route_pool_addresses":["o","c","v4"],
         "state_accounts_observed_slot":123}

def native(fixture,*,leg_index,amount_in,observed_unix):
    assert fixture is FIXTURE and observed_unix==1
    return {"venue":fixture["route_venues"][leg_index],
            "pool":fixture["route_pool_addresses"][leg_index],
            "source_slot":123,"quote_status":"SOURCE_BOUND_INDICATIVE",
            "predicted_output_base_units":amount_in+20,**SAFE}

class QuoteRankingTests(unittest.TestCase):
    @patch("arb.m5_source_triangle_quote_ranking.quote_leg",side_effect=native)
    def test_true_integer_leg_continuity_and_explicit_gross_only(self,quote):
        result=rank([FIXTURE],amount_in=100,observed_unix=1)
        self.assertEqual([call.kwargs["amount_in"] for call in quote.call_args_list],
                         [100,120,140])
        self.assertEqual(result["positive_gross"],1)
        row=result["ranked"][0]
        self.assertEqual(row["gross_delta_start_mint_base_units"],60)
        self.assertFalse(row["net_profitability_confirmed"])
        self.assertEqual(result["net_profitable_candidates"],0)
        self.assertFalse(result["broadcast"])

    @patch("arb.m5_source_triangle_quote_ranking.quote_leg",side_effect=native)
    def test_optional_net_cost_only_counts_indicative_candidates(self,quote):
        fees={"start_mint":"A","units":"START_MINT_BASE_UNITS",
              "snapshot_slot":123,"observed_unix":1,
              "estimation_method":"explicit source-mint-denominated budget",
              "network_fee":5,"priority_fee":2,"account_setup":3,
              "slippage_reserve":10,**SAFE}
        result=rank([FIXTURE],amount_in=100,observed_unix=1,
                    cost_evidence_by_index={0:fees})
        self.assertEqual(result["indicative_net_positive_candidates"],1)
        self.assertEqual(result["net_profitable_candidates"],0)
        row=result["ranked"][0]["net_cost_evaluation"]
        self.assertEqual(row["estimated_net_delta_start_mint_base_units"],40)
        self.assertFalse(row["net_profitability_confirmed"])
        self.assertFalse(row["signed_atomic_execution_verified"])
        self.assertFalse(row["broadcast"])

    @patch("arb.m5_source_triangle_quote_ranking.quote_leg",side_effect=native)
    def test_unpriced_or_wrong_currency_cost_cannot_be_profit(self,quote):
        invalid=[
            None,
            {"start_mint":"USDC","units":"START_MINT_BASE_UNITS",
             "snapshot_slot":123,"observed_unix":1,
             "estimation_method":"test", "network_fee":1,"priority_fee":1,
             "account_setup":1,"slippage_reserve":1},
            {"start_mint":"A","units":"START_MINT_BASE_UNITS",
             "snapshot_slot":122,"observed_unix":1,
             "estimation_method":"test", "network_fee":1,"priority_fee":1,
             "account_setup":1,"slippage_reserve":1},
        ]
        for cost in invalid:
            with self.subTest(cost=cost):
                result=rank([FIXTURE],amount_in=100,observed_unix=1,
                            cost_evidence_by_index={0:cost})
                self.assertEqual(result["indicative_net_positive_candidates"],0)
                self.assertEqual(result["net_profitable_candidates"],0)
                self.assertEqual(result["all_results"][0]["net_cost_evaluation"]["status"],
                                 "NET_COST_UNASSESSABLE")

    @patch("arb.m5_source_triangle_quote_ranking.quote_leg",side_effect=native)
    def test_costs_can_turn_gross_positive_into_net_negative(self,quote):
        costs={"start_mint":"A","units":"START_MINT_BASE_UNITS",
               "snapshot_slot":123,"observed_unix":1,
               "estimation_method":"source-mint-denominated estimate",
               "network_fee":15,"priority_fee":20,
               "account_setup":5,"slippage_reserve":30}
        result=rank([FIXTURE],amount_in=100,observed_unix=1,
                    cost_evidence_by_index={0:costs})
        self.assertEqual(result["positive_gross"],1)
        self.assertEqual(result["indicative_net_positive_candidates"],0)
        self.assertEqual(result["indicative_net_cost_assessed"],1)
        self.assertEqual(result["all_results"][0]["net_cost_evaluation"][
            "estimated_net_delta_start_mint_base_units"],-10)

    @patch("arb.m5_source_triangle_quote_ranking.quote_leg")
    def test_missing_native_auxiliary_blocks_route(self,quote):
        quote.return_value={"venue":"orca","pool":"o","source_slot":123,
            "quote_status":"NATIVE_QUOTE_BLOCKED","reason":"missing tick arrays",
            "predicted_output_base_units":None}
        result=rank([FIXTURE],amount_in=100,observed_unix=1)
        self.assertEqual(result["fully_quoted"],0)
        self.assertEqual(result["blocked"],1)
        self.assertIn("missing tick arrays",result["all_results"][0]["reason"])

    @patch("arb.m5_source_triangle_quote_ranking.quote_leg")
    def test_stale_source_slot_is_not_accepted(self,quote):
        quote.return_value={"venue":"orca","pool":"o","source_slot":122,
            "quote_status":"SOURCE_BOUND_INDICATIVE",
            "predicted_output_base_units":120}
        self.assertEqual(rank([FIXTURE],amount_in=100,observed_unix=1)["blocked"],1)

    def test_invalid_open_route_rejected_without_quoting(self):
        route={**FIXTURE,"route_mints":["A","B","C","D"]}
        result=rank([route],amount_in=100,observed_unix=1)
        self.assertEqual(result["blocked"],1)


if __name__=="__main__":
    unittest.main()
