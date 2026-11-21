import unittest
from arb.atomic_graph_coordinator import MAX_SOLANA_COMPUTE_UNITS,verify_signed_compute_budget
class Tests(unittest.TestCase):
    def test_realistic_signed_compute_units(self):
        self.assertEqual(verify_signed_compute_budget({"unitsConsumed":305010},stage="atomic"),305010)
    def test_exact_protocol_ceiling(self):
        self.assertEqual(verify_signed_compute_budget({"unitsConsumed":MAX_SOLANA_COMPUTE_UNITS},stage="prefix"),MAX_SOLANA_COMPUTE_UNITS)
    def test_missing_bogus_overflow_and_boolean_rejected(self):
        for amount in (None,True,0,-1,MAX_SOLANA_COMPUTE_UNITS+1,"1234",2.5):
            with self.subTest(amount=amount):
                with self.assertRaises(ValueError):
                    verify_signed_compute_budget({"unitsConsumed":amount},stage="atomic")
    def test_error_shape_rejected(self):
        with self.assertRaises(ValueError):
            verify_signed_compute_budget(None,stage="prefix")
if __name__=="__main__":unittest.main()
