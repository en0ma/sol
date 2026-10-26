"""Raydium cp-swap native CurveCalculator fee-rounding regression vectors.

Source: raydium-io/raydium-cp-swap
programs/cp-swap/src/curve/calculator.rs::swap_base_input
programs/cp-swap/src/curve/fees.rs::split_creator_fee
and states/pool.rs::is_creator_fee_on_input.

These unit vectors do not count as independently executed Surfpool swaps.
"""
import unittest
from arb.cpmm_creator_fee_quote import calculate


class NativeCreatorFeeRounding(unittest.TestCase):
    def test_input_side_combined_ceiling_prevents_double_dust_charge(self):
        result = calculate(1_000_000, 2_000_000, 101,
                           2500, 1000, 0, 0)
        # ceil(101 * 3500 / 1e6) = 1.
        # creator floor(1 * 1000 / 3500) = 0, trade fee = 1.
        # curve output floor(2_000_000 * 100 / 1_000_100) = 199.
        self.assertEqual(result["trade_fee_input_base_units"], 1)
        self.assertEqual(result["creator_fee_base_units"], 0)
        self.assertEqual(result["estimated_output_base_units"], 199)
        self.assertFalse(result["protocol_exact_verified"])

    def test_input_creator_share_is_floor_of_combined_ceiling_fee(self):
        result = calculate(1_000_000, 2_000_000, 10_000,
                           2500, 1000, 1, 0)
        self.assertEqual(result["trade_fee_input_base_units"], 25)
        self.assertEqual(result["creator_fee_base_units"], 10)
        self.assertEqual(result["creator_fee_mint_side"], "input")

    def test_output_side_takes_creator_fee_after_curve_rounding(self):
        result = calculate(1_000_000, 2_000_000, 10_000,
                           2500, 1000, 1, 1)
        curve = 2_000_000 * (10_000 - 25) // (1_000_000 + (10_000 - 25))
        expected_creator = (curve * 1000 + 1_000_000 - 1) // 1_000_000
        self.assertEqual(result["estimated_output_base_units"], curve - expected_creator)
        self.assertEqual(result["creator_fee_base_units"], expected_creator)
        self.assertEqual(result["creator_fee_mint_side"], "output")

    def test_disabled_creator_fee_does_not_resurrect_config_rate(self):
        result = calculate(1_000_000, 2_000_000, 10_000,
                           2500, 1000, 0, 0, enabled=False)
        self.assertEqual(result["creator_fee_base_units"], 0)
        self.assertEqual(result["trade_fee_input_base_units"], 25)

    def test_zero_combined_input_fee_fails_closed(self):
        with self.assertRaises(ValueError):
            calculate(1_000_000, 2_000_000, 10_000,
                      0, 0, 0, 0)


if __name__ == "__main__":
    unittest.main()
