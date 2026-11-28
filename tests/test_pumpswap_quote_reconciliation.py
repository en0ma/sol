import unittest
from unittest.mock import patch
from arb.pumpswap_quote_reconciliation import reconcile_simulation


class PumpSwapQuoteReconciliationTests(unittest.TestCase):
    def test_reject_unsigned_or_failed_simulation(self):
        with self.assertRaisesRegex(ValueError,"signed simulation"):
            reconcile_simulation({}, "base",100,
                {"simulation_verified":False,"spent_base_units":100,
                 "received_base_units":50})

    @patch("arb.pumpswap_quote_reconciliation.quote_candidate_interval")
    def test_partial_spend_uses_actual_amount(self,quote):
        quote.return_value={"candidate_outputs":{"standard":50,"stable":52}}
        r=reconcile_simulation({},"quote",100,
                               {"simulation_verified":True,
                                "spent_base_units":80,"received_base_units":50})
        quote.assert_called_once_with({},"quote",80)
        self.assertEqual(r["matching_modes"],["standard"])
        self.assertFalse(r["quote_reconciled"])
        self.assertFalse(r["actionable"])

    @patch("arb.pumpswap_quote_reconciliation.quote_candidate_interval")
    def test_mismatching_simulation_is_not_verified_quote(self,quote):
        quote.return_value={"candidate_outputs":{"standard":50,"stable":52}}
        r=reconcile_simulation({},"base",100,
                               {"simulation_verified":True,
                                "spent_base_units":100,"received_base_units":49})
        self.assertEqual(r["status"],"QUOTE_MISMATCH")
        self.assertFalse(r["profitable_arbitrage_verified"])
