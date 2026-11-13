import unittest
from unittest.mock import patch
from arb.orca_swap_v2_program_probe import classify_program, run, UPGRADEABLE_LOADER

class OrcaProgramProbeTests(unittest.TestCase):
    def test_program_must_be_executable_and_correct_owner(self):
        self.assertFalse(classify_program(None)["ready_for_pool_fixture"])
        self.assertFalse(classify_program({"executable":False,"owner":UPGRADEABLE_LOADER})["ready_for_pool_fixture"])
        self.assertFalse(classify_program({"executable":True,"owner":"wrong"})["ready_for_pool_fixture"])
        self.assertTrue(classify_program({"executable":True,"owner":UPGRADEABLE_LOADER})["ready_for_pool_fixture"])

    def test_rpc_snapshot_not_authorizing(self):
        with patch("arb.orca_swap_v2_program_probe.call", return_value={
            "context":{"slot":123}, "value":{"executable":True,"owner":UPGRADEABLE_LOADER}
        }):
            report=run("http://127.0.0.1:8899")
        self.assertEqual(report["snapshot_slot"],123)
        self.assertTrue(report["ready_for_pool_fixture"])
        self.assertFalse(report["signed_simulation_verified"])
        self.assertFalse(report["actionable"])
        self.assertFalse(report["broadcast"])

    def test_disallow_nonloopback(self):
        with self.assertRaises(ValueError):
            run("https://api.mainnet-beta.solana.com")
