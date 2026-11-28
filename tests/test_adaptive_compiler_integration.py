import unittest
from unittest.mock import patch
from arb.atomic_graph_coordinator import compile_adaptive_route
class Tests(unittest.TestCase):
    def legs(self,n):
        return [{"venue":str(i),"pool":str(i),"input_mint":str(i%2),
                 "output_mint":str((i+1)%2)} for i in range(n)]
    def compile(self,n,closed=True):
        legs=self.legs(n)
        states={(l["venue"],l["pool"]):{} for l in legs}
        return compile_adaptive_route(legs,[legs[0]["input_mint"]]+[l["output_mint"] for l in legs],
            states,states,"owner",["acc"]*(n+1),100,
            lambda i,l,x:{"signed_offline_observed":True,"output_base_units":x+1},
            require_closed=closed)
    def test_two_leg_reuses_existing_adapter(self):
        with patch("arb.atomic_graph_coordinator.build_leg",return_value="ix") as b:
            r=self.compile(2)
        self.assertEqual(r["amounts"],[100,101])
        self.assertEqual(b.call_count,2)
        self.assertFalse(r["atomic_execution_verified"])
    def test_six_leg_same_algorithm(self):
        with patch("arb.atomic_graph_coordinator.build_leg",return_value="ix") as b:
            r=self.compile(6)
        self.assertEqual(r["amounts"],[100,101,102,103,104,105])
        self.assertEqual(b.call_count,6)
    def test_open_path_requires_explicit_permission(self):
        with patch("arb.atomic_graph_coordinator.build_leg",return_value="ix"):
            r=self.compile(3,closed=False)
            self.assertEqual(len(r["instructions"]),3)
            with self.assertRaises(ValueError):self.compile(3,closed=True)
    def test_unsigned_observation_never_compiles(self):
        legs=self.legs(2);state={(l["venue"],l["pool"]):{} for l in legs}
        with patch("arb.atomic_graph_coordinator.build_leg") as b:
            with self.assertRaises(ValueError):
                compile_adaptive_route(legs,["0","1","0"],state,state,"owner",["a"]*3,10,
                                       lambda i,l,n:{"output_base_units":20})
            b.assert_not_called()
if __name__=="__main__":unittest.main()
