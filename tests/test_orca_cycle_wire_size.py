import unittest
from arb.orca_cycle_signed_simulation import transaction_size_block

class CycleWireSizeTests(unittest.TestCase):
    def test_1232_bytes_allowed(self):
        self.assertIsNone(transaction_size_block(1232))

    def test_1744_bytes_blocked_before_rpc(self):
        result=transaction_size_block(1744)
        self.assertEqual(result["status"],"BLOCKED_TRANSACTION_SIZE")
        self.assertEqual(result["bytes_over_limit"],512)
        self.assertFalse(result["signed_simulation_requested"])
        self.assertFalse(result["broadcast"])
        self.assertFalse(result["actionable"])
        self.assertFalse(result["live_execution_approved"])

    def test_invalid_size(self):
        with self.assertRaises(ValueError):
            transaction_size_block(-1)
