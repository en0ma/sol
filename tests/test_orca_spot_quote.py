import unittest
from arb.orca_spot_quote import quote_single_tick,quote_bounded_single_tick,maximum_bounded_input,Q
class WhirlpoolSpotQuoteTests(unittest.TestCase):
    def state(self):
        return {"token_mint_a":"a","token_mint_b":"b",
                "liquidity":str(10**12),"sqrt_price_x64":str(Q),
                "fee_rate_hundredths_bps":3000}
    def test_both_directions_have_nonzero_indicative_outputs(self):
        for mint in ("a","b"):
            q=quote_single_tick(self.state(),mint,1000000)
            self.assertGreater(q["estimated_output_base_units"],0)
            self.assertFalse(q["actionable"])
            self.assertFalse(q["tick_boundary_verified"])
    def test_fee_and_mint_guards(self):
        with self.assertRaises(ValueError):quote_single_tick(self.state(),"other",1000)
        with self.assertRaises(ValueError):quote_single_tick(self.state(),"a",0)
        s=self.state();s["fee_rate_hundredths_bps"]=1000000
        with self.assertRaises(ValueError):quote_single_tick(s,"a",1000)

    def test_verified_tick_bounds_are_directional_and_fail_closed(self):
        state=self.state()
        for mint in ("a","b"):
            q=quote_bounded_single_tick(state,mint,1000000,
                lower_sqrt_x64=Q-100000000000000,upper_sqrt_x64=Q+100000000000000)
            self.assertTrue(q["supplied_tick_boundary_checked"])
            self.assertFalse(q["tick_boundary_verified"])
            self.assertFalse(q["executable_quote"])
            self.assertFalse(q["actionable"])
        for mint in ("a","b"):
            with self.subTest(mint=mint):
                with self.assertRaises(ValueError):
                    quote_bounded_single_tick(state,mint,1000000,
                        lower_sqrt_x64=Q-1,upper_sqrt_x64=Q+1)
        with self.assertRaises(ValueError):
            quote_bounded_single_tick(state,"a",1000000,
                lower_sqrt_x64=Q,upper_sqrt_x64=Q)
        with self.assertRaises(ValueError):
            quote_bounded_single_tick(state,"a",1000000,
                lower_sqrt_x64="1",upper_sqrt_x64=Q+100000000)

    def test_find_largest_bounded_trade_by_direction(self):
        for mint in ("a","b"):
            with self.subTest(mint=mint):
                result=maximum_bounded_input(self.state(),mint,
                    lower_sqrt_x64=Q-100000000000,
                    upper_sqrt_x64=Q+100000000000,max_input=1000000)
                self.assertEqual(result["status"],"INDICATIVE_SIZE_BOUND")
                self.assertFalse(result["actionable"])
                self.assertFalse(result["executable_quote"])
                self.assertLess(result["max_tested_input_base_units"],1000000)
                self.assertLessEqual(result["probes"],64)
                self.assertTrue(result["search_converged"])

    def test_whole_budget_can_be_bounded(self):
        result=maximum_bounded_input(self.state(),"a",
            lower_sqrt_x64=Q-100000000000000,
            upper_sqrt_x64=Q+100000000000000,max_input=1000000)
        self.assertEqual(result["max_tested_input_base_units"],1000000)

    def test_invalid_budget_fails_closed(self):
        for budget in (0,True,1<<64):
            with self.assertRaises(ValueError):
                maximum_bounded_input(self.state(),"a",
                    lower_sqrt_x64=Q-100000000000000,
                    upper_sqrt_x64=Q+100000000000000,max_input=budget)
