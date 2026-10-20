import unittest
from unittest.mock import patch
from arb.cross_venue_sweep import sweep,evaluate
class ExpandedSweepTests(unittest.TestCase):
    def test_reason_for_failed_swap(self):
        self.assertEqual(evaluate({"cross_venue_success":False})["reason"],"SWAP_FAILED_OR_UNCLOSED")
    def test_reason_for_loss(self):
        self.assertEqual(evaluate({"cross_venue_success":True,"residual_usdc_base_units":0,
          "venues_executed":2,"simulation_did_not_persist":True,"signed_simulation_requested":True,"net_wsol_change_lamports":-900})["reason"],"BELOW_MINIMUM_NET_PROFIT")
    @patch("arb.cross_venue_sweep.run")
    def test_best_excludes_failed(self,run):
        def fake(rpc,orca,raydium,max_wsol,size,reverse=False):
            if size==2000:return {"cross_venue_success":False}
            return {"cross_venue_success":True,"residual_usdc_base_units":0,
                    "venues_executed":2,"net_wsol_change_lamports":size-5000}
        run.side_effect=fake
        out=sweep("rpc","orca","raydium",(1000,2000,3000))
        self.assertEqual(out["best_simulated_size_usdc_base_units"],3000)
        self.assertEqual(out["profitable_candidates"],0)
