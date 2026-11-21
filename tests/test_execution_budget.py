import unittest
from arb.execution_budget import assess, ExecutionBudget

class ExecutionBudgetTests(unittest.TestCase):
    def test_profitable_and_above_minimum(self):
        result = assess(10300, ExecutionBudget(10000, 10200, 20, 30, 10))
        self.assertTrue(result["accept"])
        self.assertEqual(result["net_profit_base_units"], 240)

    def test_below_minimum_rejected_even_with_profit(self):
        self.assertFalse(assess(10300, ExecutionBudget(10000, 10400, 10, 10))["accept"])

    def test_fee_consumes_profit(self):
        self.assertFalse(assess(10100, ExecutionBudget(10000, 10000, 50, 50))["accept"])

    def test_bad_amounts_rejected(self):
        with self.assertRaises(ValueError):
            assess(100, ExecutionBudget(0, 0, 0, 0))
        with self.assertRaises(TypeError):
            assess(100.4, ExecutionBudget(100, 100, 0, 0))
