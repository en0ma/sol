import unittest
from unittest.mock import patch
from arb.m5_three_venue_signed_quote_parity import compare
class Tests(unittest.TestCase):
    @patch("arb.m5_three_venue_signed_quote_parity.accept",return_value=True)
    @patch("arb.m5_three_venue_signed_quote_parity.quote_from_fixture")
    def test_native_fee_rounding_interval_measured_against_signed_output(self,quote,_):
        f={"route_mints":["A","B","C","A"],"route_venues":["orca","raydium_cpmm","raydium_amm_v4"],
          "route_pool_addresses":["p","q","r"],"state_accounts_observed_slot":22}
        receipt={"planned_inputs":[100,90,80],"initial_balances_base_units":[100,0,0,0],
          "positive_post_balances_base_units":[0,0,0,120],
          "cpi_hops":[{"hop":1,"received_base_units":90,"consumed_base_units":90},
          {"hop":2,"received_base_units":80,"consumed_base_units":80}]}
        quote.return_value={"quote":{"venue":"raydium_amm_v4","pool":"r",
          "input_mint":"C","output_mint":"A","snapshot_slot":22,
          "amount_in":80,"amount_out":119},
          "native_fee_fraction_reference":{"fee_numerator":1,"fee_denominator":3000,
           "fee_floor_input_units":0,"fee_ceiling_input_units":1}}
        r=compare(f,receipt,observed_unix=100)
        self.assertEqual(r["leg_comparisons"][2]["native_fee_input_units_interval"],[0,1])
        self.assertEqual(r["native_fraction_fee_rounding_uncertainty_input_units"],1)
        self.assertEqual(r["leg_comparisons"][2]["signed_minus_quote_base_units"],1)
        self.assertEqual(r["independently_validated_quote_samples"],0)
if __name__=="__main__":unittest.main()
