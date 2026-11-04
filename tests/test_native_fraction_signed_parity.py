import unittest
from unittest.mock import patch
from arb.m5_three_venue_signed_quote_parity import compare
class Tests(unittest.TestCase):
    @patch("arb.m5_three_venue_signed_quote_parity.accept",return_value=True)
    @patch("arb.m5_three_venue_signed_quote_parity.quote_from_fixture")
    def test_native_fee_fraction_is_retained_with_actual_signed_v4_leg(self,quote,_):
        f={"route_mints":["A","B","C","A"],
           "route_venues":["orca","raydium_cpmm","raydium_amm_v4"],
           "route_pool_addresses":["p","q","r"],
           "state_accounts_observed_slot":30}
        r={"planned_inputs":[100,90,80],
           "initial_balances_base_units":[100,0,0,0],
           "positive_post_balances_base_units":[0,0,0,120],
           "cpi_hops":[{"hop":1,"received_base_units":90,"consumed_base_units":90},
                       {"hop":2,"received_base_units":80,"consumed_base_units":80}]}
        quote.return_value={"quote":{"venue":"raydium_amm_v4",
           "pool":"r","input_mint":"C","output_mint":"A",
           "amount_in":80,"amount_out":119,"snapshot_slot":30,
           "quote_model":"AMM_V4_NATIVE_FRACTION_ADJUSTED_RESERVE_INDICATIVE"},
           "native_fee_fraction_reference":{"fee_numerator":1,
                 "fee_denominator":3000,"fee_floor_input_units":0,
                 "fee_ceiling_input_units":1}}
        out=compare(f,r,observed_unix=1)
        leg=out["leg_comparisons"][2]
        self.assertEqual(leg["signed_minus_quote_base_units"],1)
        self.assertEqual(leg["native_fee_denominator"],3000)
        self.assertEqual(out["native_fraction_signed_legs_compared"],1)
        self.assertEqual(out["independently_validated_quote_samples"],0)
if __name__=="__main__":unittest.main()
