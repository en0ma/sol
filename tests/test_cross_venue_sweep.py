import unittest
from unittest.mock import patch
from arb.cross_venue_sweep import evaluate,sweep
class SweepTests(unittest.TestCase):
    def test_negative_pnl_rejected(self):
        self.assertFalse(evaluate({"cross_venue_success":True,
            "residual_usdc_base_units":0,"venues_executed":2,"simulation_did_not_persist":True,"signed_simulation_requested":True,
            "net_wsol_change_lamports":-1})["simulated_profitable"])
    def test_profitable_still_not_live_approved(self):
        r=evaluate({"cross_venue_success":True,"residual_usdc_base_units":0,
            "venues_executed":2,"simulation_did_not_persist":True,"signed_simulation_requested":True,"net_wsol_change_lamports":10001})
        self.assertTrue(r["simulated_profitable"])
        self.assertFalse(r["live_execution_approved"])
    def test_residual_token_blocks(self):
        self.assertFalse(evaluate({"cross_venue_success":True,
            "residual_usdc_base_units":1,"venues_executed":2,
            "net_wsol_change_lamports":999999})["simulated_profitable"])
    @patch("arb.cross_venue_sweep.run")
    def test_sweep_calls_real_simulator(self,run):
        run.return_value={"cross_venue_success":True,
             "residual_usdc_base_units":0,"venues_executed":2,
             "net_wsol_change_lamports":-5}
        r=sweep("rpc","orca","raydium",(1000,10000))
        self.assertEqual(run.call_count,2)
        self.assertEqual(r["profitable_candidates"],0)
    def test_rejects_unbounded_sizes(self):
        with self.assertRaises(ValueError):
            sweep("rpc","orca","raydium",(1,)*9)
