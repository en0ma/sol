"""Regression checks for signed SwapV2 negative-control error classification."""
import unittest
from unittest.mock import patch
from arb.orca_swap_v2_offline_negative_control import require_pool_rejection_error, run

class SwapV2NegativeControlErrorTests(unittest.TestCase):
    def test_unavailable_program_is_not_pool_rejection(self):
        for error in ("InvalidProgramForExecution", "ProgramAccountNotFound",
                      "AccountNotFound", "BlockhashNotFound",
                      "SignatureFailure", "InsufficientFundsForFee"):
            with self.subTest(error=error):
                with self.assertRaisesRegex(ValueError, "before pool validation"):
                    require_pool_rejection_error(error)

    def test_offline_missing_program_reports_blocked_not_rejected(self):
        responses=[{}, {"value":{"blockhash":"11111111111111111111111111111111"}},
                   {"value":{"err":"InvalidProgramForExecution"}}]
        with patch("arb.orca_swap_v2_offline_negative_control.call", side_effect=responses), \
             patch.dict("os.environ", {"SURFPOOL_EXPLICITLY_OFFLINE":"1"}):
            report=run("http://127.0.0.1:8899")
        self.assertEqual(report["status"],"SWAP_V2_NEGATIVE_CONTROL_BLOCKED")
        self.assertEqual(report["blocker"],"ORCA_PROGRAM_NOT_EXECUTABLE")
        self.assertFalse(report["rejected"])
        self.assertFalse(report["signed_swap_simulation_verified"])
        self.assertFalse(report["broadcast"])

    def test_other_error_is_preserved_as_diagnostic_not_success(self):
        self.assertEqual(
            require_pool_rejection_error({"InstructionError": [0, "InvalidAccountData"]}),
            "{'InstructionError': [0, 'InvalidAccountData']}",
        )

if __name__ == "__main__":
    unittest.main()
