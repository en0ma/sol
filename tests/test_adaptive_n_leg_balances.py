import unittest
from arb.atomic_graph_coordinator import audit_n_leg_balances
class Tests(unittest.TestCase):
    def test_six_hop_reconciles(self):
        a=audit_n_leg_balances([100,90,80,70,60,50],[100,0,0,0,0,0,0],[0,0,0,0,0,0,40],rollback_balances=[100,0,0,0,0,0,0],later_instruction_failed=True)
        self.assertEqual(a["status"],"N_LEG_BALANCES_AND_ROLLBACK_RECONCILED")
        self.assertFalse(a["signed_cpi_per_leg_verified"])
    def test_residual_fails(self):
        a=audit_n_leg_balances([100,90,80],[100,0,0,0],[0,3,0,40],rollback_balances=[100,0,0,0],later_instruction_failed=True)
        self.assertEqual(a["status"],"UNVERIFIED")
    def test_missing_negative_control_fails(self):
        a=audit_n_leg_balances([100,90],[100,0,0],[0,0,40])
        self.assertEqual(a["status"],"UNVERIFIED")
    def test_malformed_inventory_fails(self):
        with self.assertRaises(ValueError):audit_n_leg_balances([100,90],[100,0],[0,0])
if __name__=="__main__":unittest.main()
