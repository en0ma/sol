import unittest
from unittest.mock import patch
from arb.m5_three_venue_signed_quote_parity import compare
class Tests(unittest.TestCase):
    def source(self):
        return {"route_venues":["raydium_cpmm","orca","raydium_amm_v4"],
                "route_pool_addresses":["a","b","c"],
                "route_mints":["A","B","C","A"],"state_accounts_observed_slot":9}
    def receipt(self):
        return {"planned_inputs":[100,80,60],
                "cpi_hops":[{"hop":1,"received_base_units":80,"consumed_base_units":80},
                            {"hop":2,"received_base_units":60,"consumed_base_units":60}],
                "initial_balances_base_units":[100,0,0,0],
                "positive_post_balances_base_units":[0,0,0,65]}
    @patch("arb.m5_three_venue_signed_quote_parity.accept",return_value={})
    @patch("arb.m5_three_venue_signed_quote_parity.quote_cpmm_only",
           return_value={"quote":{"venue":"raydium_cpmm","pool":"a",
           "input_mint":"A","output_mint":"B","amount_in":100,
           "snapshot_slot":9,"amount_out":79}})
    @patch("arb.m5_three_venue_signed_quote_parity.quote_from_fixture",
           return_value={"quote":{"venue":"raydium_amm_v4","pool":"c",
           "input_mint":"C","output_mint":"A","amount_in":60,
           "snapshot_slot":9,"amount_out":64}})
    def test_real_signed_inputs_probed_without_false_accuracy(self,v4,cpmm,accept):
        r=compare(self.source(),self.receipt(),observed_unix=99)
        self.assertTrue(r["signed_execution_accepted"])
        self.assertEqual(r["independently_validated_quote_samples"],0)
        self.assertEqual(len(r["leg_comparisons"]),3)
        self.assertEqual(r["leg_comparisons"][1]["quoted_output_base_units"],None)
        self.assertEqual(r["leg_comparisons"][0]["quoted_output_base_units"],79)
        self.assertEqual(r["leg_comparisons"][2]["signed_output_base_units"],65)
        self.assertTrue(all(not x["quote_verified"] for x in r["leg_comparisons"]))
    @patch("arb.m5_three_venue_signed_quote_parity.accept",side_effect=ValueError("bad"))
    def test_unverified_signed_transaction_never_quoted(self,_):
        r=compare(self.source(),self.receipt(),observed_unix=99)
        self.assertFalse(r["signed_execution_accepted"])
        self.assertEqual(r["leg_comparisons"],[])
if __name__=="__main__":unittest.main()
