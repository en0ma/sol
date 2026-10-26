import unittest
from unittest.mock import patch
from arb.m5_three_venue_signed_quote_parity import compare
class PrecisionTests(unittest.TestCase):
    @patch("arb.m5_three_venue_signed_quote_parity.accept",return_value=True)
    @patch("arb.m5_three_venue_signed_quote_parity.quote_cpmm_only")
    @patch("arb.m5_three_venue_signed_quote_parity.quote_from_fixture")
    def test_one_unit_mismatch_not_misrepresented_as_exact_match(self,v4,cpmm,_):
        source={"route_mints":["A","B","C","A"],
                "route_venues":["raydium_cpmm","orca","raydium_amm_v4"],
                "route_pool_addresses":["a","b","c"],
                "state_accounts_observed_slot":10}
        receipt={"planned_inputs":[100000000,90000000,80000000],
                "initial_balances_base_units":[100000000,0,0,0],
                "positive_post_balances_base_units":[0,0,0,75000000],
                "cpi_hops":[{"hop":1,"received_base_units":90000000,
                             "consumed_base_units":90000000},
                            {"hop":2,"received_base_units":80000000,
                             "consumed_base_units":80000000}]}
        cpmm.return_value={"native_fee_rounding_reference":{"output_interval_base_units":[89999998,90000000]},
            "quote":{"venue":"raydium_cpmm","pool":"a",
          "input_mint":"A","output_mint":"B","snapshot_slot":10,
          "amount_in":100000000,"amount_out":89999999}}
        v4.return_value={"quote":{"venue":"raydium_amm_v4","pool":"c",
          "input_mint":"C","output_mint":"A","snapshot_slot":10,
          "amount_in":80000000,"amount_out":75000000}}
        result=compare(source,receipt,observed_unix=100)
        self.assertEqual(result["quoted_leg_count"],2)
        self.assertTrue(result["leg_comparisons"][0]["signed_output_inside_cpmm_fee_rounding_interval"])
        self.assertEqual(result["cpmm_source_fee_rounding_signed_legs_compared"],1)
        self.assertEqual(result["exact_integer_indicative_matches"],1)
        self.assertEqual(result["nonzero_errors_hidden_by_truncated_bps"],1)
        self.assertEqual(result["leg_comparisons"][0]["signed_minus_quote_base_units"],1)
        self.assertEqual(result["leg_comparisons"][0]["deviation_bps_ceiling"],1)
        self.assertEqual(result["independently_validated_quote_samples"],0)
if __name__=="__main__":unittest.main()
