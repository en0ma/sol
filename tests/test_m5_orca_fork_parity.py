import unittest
from unittest.mock import patch
from arb.m5_orca_fork_parity import compare_orca

SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}

class SignedOrcaClockBlockerTests(unittest.TestCase):
    @patch("arb.m5_orca_fork_parity.assess")
    @patch("arb.m5_orca_fork_parity.extract_pool_states")
    @patch("arb.m5_orca_fork_parity.quote_leg")
    def test_clock_absent_retains_signed_result_without_false_quote_success(
            self,quote,rows,assess):
        rows.return_value=[
            {"venue":"raydium_amm_v4","address":"a"},
            {"venue":"raydium_clmm","address":"b"},
            {"venue":"meteora_dlmm","address":"c"},
            {"venue":"orca","address":"d"}]
        assess.return_value={"status":"VERIFIED_SIGNED_FOUR_TO_SIX_HOP_ROLLBACK"}
        receipt={"planned_inputs":[10000,17000,12000,500],
                 "positive_post_balances_base_units":[0,0,0,0,480],
                 **SAFE}
        f={"state_accounts_observed_slot":100,**SAFE}
        report=compare_orca(f,{10000:receipt},observed_unix=5)
        self.assertEqual(report["status"],"ORCA_FORK_SIGNED_NATIVE_PARITY_BLOCKED_CLOCK")
        self.assertEqual(report["clock_blocked_size_count"],1)
        self.assertEqual(report["exact_match_count"],0)
        self.assertFalse(report["all_signed_sizes_parity_verified"])
        quote.assert_not_called()
        self.assertFalse(report["broadcast"])

    @patch("arb.m5_orca_fork_parity.assess")
    @patch("arb.m5_orca_fork_parity.extract_pool_states")
    @patch("arb.m5_orca_fork_parity.quote_leg")
    def test_source_clock_is_passed_to_native_orca_quote(self,quote,rows,assess):
        rows.return_value=[
            {"venue":"raydium_amm_v4","address":"a"},
            {"venue":"raydium_clmm","address":"b"},
            {"venue":"meteora_dlmm","address":"c"},
            {"venue":"orca","address":"d"}]
        assess.return_value={"status":"VERIFIED_SIGNED_FOUR_TO_SIX_HOP_ROLLBACK"}
        quote.return_value={"venue":"orca","pool":"d","source_slot":100,
                            "quote_status":"SOURCE_BOUND_INDICATIVE",
                            "predicted_output_base_units":480,**SAFE}
        clock={"status":"ORCA_FORK_CLOCK_STABLE_FOR_SIGNED_ATTEMPT",
               "fork_clock_stable_for_quote":True,"fork_unix_timestamp":1793149190,
               **SAFE}
        receipt={"planned_inputs":[10000,17000,12000,500],
                 "positive_post_balances_base_units":[0,0,0,0,480],
                 "orca_fork_clock_evidence":clock,**SAFE}
        f={"state_accounts_observed_slot":100,**SAFE}
        report=compare_orca(f,{10000:receipt},observed_unix=5)
        self.assertTrue(report["all_signed_sizes_parity_verified"])
        self.assertEqual(report["exact_match_count"],1)
        self.assertEqual(quote.call_args.kwargs["observed_unix"],1793149190)
