import unittest
from unittest.mock import patch
from arb.atomic_graph_coordinator import compile_adaptive_route
class Tests(unittest.TestCase):
    def test_final_venue_is_compiled_without_fake_standalone_observation(self):
        legs=[{"venue":"orca","pool":"p","input_mint":"A","output_mint":"B"},
              {"venue":"raydium_cpmm","pool":"q","input_mint":"B","output_mint":"A"}]
        state={(l["venue"],l["pool"]):{} for l in legs}
        calls=[]
        def observe(i,leg,n):
            calls.append((i,n))
            return {"signed_offline_observed":True,"output_base_units":37,"compute_units":400}
        with patch("arb.atomic_graph_coordinator.build_leg",return_value="ix") as builder:
            plan=compile_adaptive_route(legs,["A","B","A"],state,state,
                 "owner",["src","mid","dst"],100,observe)
        self.assertEqual(calls,[(0,100)])
        self.assertEqual(plan["amounts"],[100,37])
        self.assertEqual(plan["observations"][0]["compute_units"],400)
        self.assertEqual(builder.call_count,2)
        self.assertFalse(plan["atomic_execution_verified"])
if __name__=="__main__":unittest.main()
