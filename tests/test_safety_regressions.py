"""CI safeguards for the research-only arbitrage implementation."""
import unittest
from arb.core import Quote, evaluate_cycle

class SafetyRegressionTests(unittest.TestCase):
    def test_rejects_open_route(self):
        with self.assertRaises(ValueError):
            evaluate_cycle([Quote("Raydium CLMM", "SOL", "USDC", 100, 200)], 100)

    def test_rejects_negative_cost(self):
        with self.assertRaises(ValueError):
            evaluate_cycle([Quote("Raydium CLMM", "SOL", "SOL", 100, 100)], 100, -1)

    def test_breakeven_not_profitable(self):
        route = [Quote("Raydium CLMM", "SOL", "USDC", 100, 200),
                 Quote("Raydium CPMM", "USDC", "SOL", 200, 101)]
        self.assertFalse(evaluate_cycle(route, 100, 1)["profitable"])

    def test_rejects_zero_amount(self):
        with self.assertRaises(ValueError):
            evaluate_cycle([Quote("Raydium CPMM", "SOL", "SOL", 0, 1)], 0)

if __name__ == "__main__":
    unittest.main()
