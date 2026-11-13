import unittest
from arb.orca_tick_math import Q, sqrt_price_from_tick_index
from arb.orca_crossing_budget import first_crossing_budget


class OrcaCrossingBudgetTests(unittest.TestCase):
    def state(self):
        return {"token_mint_a":"a","token_mint_b":"b",
                "tick_current_index":1,"tick_spacing":1,
                "sqrt_price_x64":str(sqrt_price_from_tick_index(1)),
                "liquidity":str(10**12),"fee_rate_hundredths_bps":3000}

    def test_first_upper_tick_budget_is_positive_and_non_actionable(self):
        arrays=[{"start_tick":0,"status":"FIXED_VALID",
                 "ticks":[{"tick_index":10,"liquidity_net":"0"}]}]
        q=first_crossing_budget(self.state(),"b",arrays)
        self.assertEqual(q["status"],"CROSSING_BUDGET_ESTIMATE")
        self.assertEqual(q["first_tick"],10)
        self.assertGreater(q["candidate_input_base_units"],0)
        self.assertFalse(q["actionable"])
        self.assertFalse(q["executable_quote"])

    def test_known_missing_array_keeps_gap(self):
        arrays=[{"start_tick":0,"status":"FIXED_VALID","ticks":[]},
                {"start_tick":88,"status":"MISSING"}]
        q=first_crossing_budget(self.state(),"b",arrays)
        self.assertEqual(q["status"],"UNKNOWN_ARRAY_GAP")
        self.assertIsNone(q["candidate_input_base_units"])

    def test_cap_and_invalid_inputs(self):
        arrays=[{"start_tick":0,"status":"FIXED_VALID",
                 "ticks":[{"tick_index":10,"liquidity_net":"0"}]}]
        q=first_crossing_budget(self.state(),"b",arrays,simulation_cap=100)
        self.assertFalse(q["within_simulation_cap"])
        with self.assertRaises(ValueError):
            first_crossing_budget(self.state(),"b",arrays,simulation_cap=True)
        with self.assertRaises(ValueError):
            first_crossing_budget(self.state(),"unknown",arrays)
