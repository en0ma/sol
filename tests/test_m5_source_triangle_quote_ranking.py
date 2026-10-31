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
