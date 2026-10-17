import unittest
from arb.raydium_clmm_quote_reconciliation import compare

class QuoteReconciliationTests(unittest.TestCase):
    def test_measured_shortfall_is_not_profit(self):
        q={"status":"INDICATIVE_WITHIN_TICK_ONLY","actionable":False,
           "estimated_output_base_units":185241}
        s={"simulation_verified":True,"received_base_units":183223}
        result=compare(q,s)
        self.assertEqual(result["observed_minus_estimated_base_units"],-2018)
        self.assertGreater(result["absolute_error_bps_of_observed"],100)
        self.assertFalse(result["atomic_cycle_simulated"])
        self.assertFalse(result["profitable_arbitrage_verified"])

    def test_rejects_unverified_execution_or_fake_quote(self):
        q={"status":"INDICATIVE_WITHIN_TICK_ONLY","actionable":False,
           "estimated_output_base_units":10}
        with self.assertRaises(ValueError):compare(q,{"received_base_units":11})
        with self.assertRaises(ValueError):compare({**q,"actionable":True},
            {"received_base_units":11,"simulation_verified":True})
