import unittest
from unittest.mock import patch,MagicMock
from arb.atomic_graph_coordinator import simulate_adaptive_n_leg_offline
class Tests(unittest.TestCase):
    def test_no_negative_control_never_promotes_success(self):
        legs=[{"venue":"raydium_cpmm","pool":"p","input_mint":"A","output_mint":"B"},
              {"venue":"orca","pool":"q","input_mint":"B","output_mint":"A"}]
        with patch("arb.damm_cpmm_atomic_offline._post",return_value=[100,0,0]),patch(
            "arb.atomic_graph_coordinator.compile_adaptive_route",return_value={
            "instructions":["one","two"],"amounts":[100,80]}),patch(
            "arb.atomic_graph_coordinator.sign_adaptive_n_leg_offline",
            return_value=(MagicMock(),None,{"instruction_order_verified":True})),patch(
            "arb.damm_cpmm_atomic_offline._simulate",return_value=({"err":None,"logs":[]},250)),patch(
            "arb.next_ten_signed_atomic_offline.top_level_events",return_value=[
            ["cpmm","invoke"],["cpmm","success"],["orca","invoke"],["orca","success"]]),patch(
            "arb.atomic_graph_coordinator.audit_n_leg_cpi",return_value={"hops":[{"hop":1}]}),patch(
            "arb.atomic_graph_coordinator.signed_n_leg_post_balances",return_value=[0,0,75]),patch(
            "arb.next_ten_fork_pool_probe.PROGRAMS",{"raydium_cpmm":"cpmm","orca":"orca"}):
            report=simulate_adaptive_n_leg_offline("http://127.0.0.1:8899",legs,
                ["A","B","A"],{},{},"owner",["x","y","z"],100,lambda *x:None,MagicMock())
        self.assertEqual(report["status"],"NEGATIVE_CONTROL_MISSING")
        self.assertFalse(report["signed_atomic_simulation_verified"])
    def test_reused_token_account_rejected(self):
        with self.assertRaises(ValueError):
            simulate_adaptive_n_leg_offline("http://127.0.0.1:8899",
                [{}]*2,["A","B","A"],{},{},"owner",["x","x","y"],
                100,None,None)
if __name__=="__main__":unittest.main()
