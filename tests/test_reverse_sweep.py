import unittest
from unittest.mock import patch
from arb.cross_venue_sweep import sweep
class ReverseSweepTests(unittest.TestCase):
    @patch("arb.cross_venue_sweep.run")
    def test_reverse_passed_to_simulator(self,run):
        run.return_value={"cross_venue_success":False,"residual_usdc_base_units":0}
        report=sweep("rpc","orca","raydium",(1000,),reverse=True)
        self.assertEqual(report["direction"],"raydium_to_orca")
        run.assert_called_once_with("rpc","orca","raydium",1000000,1000,reverse=True)
