import unittest
from unittest.mock import patch
from arb.token_cycle_tick_preflight import preflight
from arb.orca_whirlpool import SOL, USDC

def graph():
    return {"cycles":[{"tokens":[SOL,USDC,SOL],
            "all_pools_onchain_verified": True,
            "legs":[{"venue":"orca","pool":"a","from":SOL,"to":USDC},
                    {"venue":"orca","pool":"b","from":USDC,"to":SOL}]}]}

class TickPreflightTests(unittest.TestCase):
    @patch("arb.token_cycle_tick_preflight.inspect_swap_requirements")
    @patch("arb.token_cycle_tick_preflight.fetch_pool")
    def test_each_leg_uses_mint_order_and_directional_ticks(self, fetch, inspect):
        fetch.return_value={"token_mint_a":SOL,"token_mint_b":USDC}
        inspect.return_value={"directions":{"a_to_b":{"available":True,"required_starts":[0,1,2]},
                                            "b_to_a":{"available":True,"required_starts":[3,4,5]}}}
        result=preflight("http://127.0.0.1:8899",graph())
        self.assertEqual(result["routes_with_ready_ticks"],1)
        self.assertEqual([c["direction"] for c in result["routes"][0]["checks"]],
                         ["a_to_b","b_to_a"])
        self.assertFalse(result["routes"][0]["signed_simulation_completed"])
        self.assertFalse(result["actionable"])

    @patch("arb.token_cycle_tick_preflight.inspect_swap_requirements")
    @patch("arb.token_cycle_tick_preflight.fetch_pool")
    def test_one_missing_tick_blocks_cycle(self,fetch,inspect):
        fetch.return_value={"token_mint_a":SOL,"token_mint_b":USDC}
        inspect.return_value={"directions":{"a_to_b":{"available":True,"required_starts":[]},
                                            "b_to_a":{"available":False,"required_starts":[9]}}}
        result=preflight("http://127.0.0.1:8899",graph())
        self.assertEqual(result["routes_with_ready_ticks"],0)
        self.assertEqual(result["routes"][0]["status"],"TICKS_UNAVAILABLE")
