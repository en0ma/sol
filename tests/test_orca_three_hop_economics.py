import unittest
from arb.orca_three_hop_offline_simulation import assess_cycle_economics

class CycleEconomicsTests(unittest.TestCase):
    def test_actual_ci_1571_loss_is_fail_closed(self):
        r=assess_cycle_economics(1000000,975490,5000)
        self.assertEqual(r["gross_wsol_change_lamports"],-24510)
        self.assertEqual(r["net_after_estimated_network_fee_lamports"],-29510)
        self.assertEqual(r["status"],"SIMULATED_LOSS")
        self.assertFalse(r["actionable"])
        self.assertFalse(r["broadcast"])
    def test_unknown_fee_never_implies_profit(self):
        r=assess_cycle_economics(1000000,1010000,None)
        self.assertIsNone(r["net_after_estimated_network_fee_lamports"])
        self.assertEqual(r["status"],"UNVERIFIED_NET_PROFIT")
        self.assertFalse(r["profitable_after_estimated_fee"])
    def test_positive_profit_still_nonactionable(self):
        r=assess_cycle_economics(1000000,1010000,5000)
        self.assertEqual(r["status"],"SIMULATED_POSITIVE_NOT_ACTIONABLE")
        self.assertFalse(r["live_execution_approved"])
    def test_invalid_fee_rejected(self):
        with self.assertRaises(ValueError):
            assess_cycle_economics(1000000,990000,-1)
