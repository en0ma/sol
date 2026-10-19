import unittest
from arb.orca_swap_v2_offline_token_runtime_probe import classify_token_runtime_simulation

class OfflineTokenRuntimeClassificationTests(unittest.TestCase):
    def test_success_and_error_are_distinct(self):
        self.assertEqual(classify_token_runtime_simulation({"err": None}),
                         "TOKEN_TRANSFER_SIMULATION_ACCEPTED")
        self.assertEqual(classify_token_runtime_simulation({"err": "InvalidProgramForExecution"}),
                         "TOKEN_TRANSFER_SIMULATION_REJECTED")

    def test_missing_simulation_result_fails_closed(self):
        with self.assertRaises(ValueError):
            classify_token_runtime_simulation(None)
