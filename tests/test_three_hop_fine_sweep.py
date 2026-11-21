import unittest
from unittest.mock import patch
from arb.three_hop_cycle import sweep
class FineSweepTests(unittest.TestCase):
    @patch("arb.three_hop_cycle.run")
    def test_closest_valid_residual(self,run):
        run.side_effect=[
            {"status":"RESIDUAL_INTERMEDIATE","ray_received":100,"cycle_closed":False},
            {"status":"RESIDUAL_INTERMEDIATE","ray_received":17,"cycle_closed":False},
            {"status":"SIMULATION_FAILED","cycle_closed":False}]
        out=sweep("rpc","cp","cl","orca",(92000,93000,94000))
        self.assertEqual(out["closest_residual_trial"]["orca_output_lamports"],93000)
        self.assertFalse(out["profitable"])
