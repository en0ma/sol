import unittest
from unittest.mock import patch
from arb.three_hop_cycle import sweep
class SweepTests(unittest.TestCase):
    @patch("arb.three_hop_cycle.run")
    def test_no_false_closed_cycle_on_residual(self,run):
        run.side_effect=[{"status":"RESIDUAL_INTERMEDIATE","ray_received":383,
                          "gross_wsol_change_lamports":-7249,"cycle_closed":False},
                         {"status":"SIMULATION_FAILED","cycle_closed":False}]
        out=sweep("rpc","cp","cl","orca",(90000,100000))
        self.assertEqual(out["status"],"NO_CLOSED_CYCLE")
        self.assertEqual(out["closest_residual_trial"]["residual_ray_base_units"],383)
        self.assertFalse(out["profitable"])
    @patch("arb.three_hop_cycle.run")
    def test_unknown_fee_not_profitable(self,run):
        run.return_value={"status":"PASS","cycle_closed":True,"ray_received":0,
                          "gross_wsol_change_lamports":5,"net_wsol_change_lamports":None}
        out=sweep("rpc","cp","cl","orca",(90000,))
        self.assertTrue(out["closed_cycle_simulated"])
        self.assertFalse(out["profitable"])
