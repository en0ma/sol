import unittest
from arb.core import Quote, evaluate_cycle

A="USDC"
B="SOL"
C="MEME"

class ArbitrageTests(unittest.TestCase):
    def test_profitable_triangle(self):
        quotes = [Quote("Meteora DLMM", A, C, 100_000_000, 200_000_000),
                  Quote("Pump.fun AMM", C, B, 200_000_000, 600_000_000),
                  Quote("Orca Whirlpools", B, A, 600_000_000, 101_500_000)]
        result = evaluate_cycle(quotes, 100_000_000, 500_000)
        self.assertEqual(result["gross_profit_units"], 1_500_000)
        self.assertEqual(result["estimated_net_units"], 1_000_000)
        self.assertTrue(result["profitable"])

    def test_cost_turns_profit_into_loss(self):
        quotes = [Quote("DEX1", A, B, 100, 200),
                  Quote("DEX2", B, A, 200, 101)]
        self.assertFalse(evaluate_cycle(quotes, 100, 2)["profitable"])

    def test_mismatched_mint_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_cycle([Quote("DEX1", A, B, 100, 200),
                            Quote("DEX2", C, A, 200, 110)], 100)

    def test_mismatched_amount_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_cycle([Quote("DEX1", A, B, 100, 200),
                            Quote("DEX2", B, A, 199, 110)], 100)

if __name__ == "__main__":
    unittest.main()
