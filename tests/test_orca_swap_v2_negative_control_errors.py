"""Regression checks for signed SwapV2 negative-control error classification."""
import unittest
from arb.orca_swap_v2_offline_negative_control import require_pool_rejection_error

class SwapV2NegativeControlErrorTests(unittest.TestCase):
    def test_unavailable_program_is_not_pool_rejection(self):
        for error in ("InvalidProgramForExecution", "ProgramAccountNotFound",
                      "AccountNotFound", "BlockhashNotFound",
                      "SignatureFailure", "InsufficientFundsForFee"):
            with self.subTest(error=error):
                with self.assertRaisesRegex(ValueError, "before pool validation"):
                    require_pool_rejection_error(error)

    def test_other_error_is_preserved_as_diagnostic_not_success(self):
        self.assertEqual(
            require_pool_rejection_error({"InstructionError": [0, "InvalidAccountData"]}),
            "{'InstructionError': [0, 'InvalidAccountData']}",
        )

if __name__ == "__main__":
    unittest.main()
