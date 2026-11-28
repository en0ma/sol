"""Regression coverage for the venue-owned CPMM creator-fee quote path.

No legacy trade-fee-only mock is permitted to substitute for missing source
creator-fee state; signed matching alone does not authenticate exact pricing.
"""
import unittest
from unittest.mock import patch
from arb.m5_three_venue_signed_quote_parity import compare


class Tests(unittest.TestCase):
    def setUp(self):
        self.fixture = {
            "route_mints": ["A", "B", "C", "A"],
            "route_venues": ["raydium_cpmm", "orca", "raydium_amm_v4"],
            "route_pool_addresses": ["cp", "or", "v4"],
            "state_accounts_observed_slot": 9,
        }
        self.receipt = {
            "planned_inputs": [100, 90, 80],
            "initial_balances_base_units": [100, 0, 0, 0],
            "positive_post_balances_base_units": [0, 0, 0, 120],
            "cpi_hops": [
                {"hop": 1, "received_base_units": 90, "consumed_base_units": 90},
                {"hop": 2, "received_base_units": 80, "consumed_base_units": 80},
            ],
        }

    @patch("arb.m5_three_venue_signed_quote_parity.accept", return_value=True)
    @patch("arb.m5_three_venue_signed_quote_parity.quote_cpmm_creator_fee_source")
    def test_creator_fee_quote_is_bound_to_signed_input_and_remains_indicative(self, quote, _):
        quote.return_value = {
            "quote": {
                "venue": "raydium_cpmm", "pool": "cp",
                "input_mint": "A", "output_mint": "B",
                "amount_in": 100, "amount_out": 90, "snapshot_slot": 9,
            },
            "venue_fee_detail": {
                "trade_fee_input_base_units": 1,
                "creator_fee_base_units": 1,
                "creator_fee_mint_side": "input",
                "protocol_exact_verified": False,
            },
            "protocol_exact_verified": False,
        }
        report = compare(self.fixture, self.receipt, observed_unix=1)
        quote.assert_called_once_with(
            self.fixture, observed_unix=1,
            leg={"venue": "raydium_cpmm", "pool": "cp",
                 "input_mint": "A", "output_mint": "B"}, amount_in=100,
        )
        row = report["leg_comparisons"][0]
        self.assertEqual(row["venue_native_fee_detail"]["creator_fee_base_units"], 1)
        self.assertTrue(row["signed_quote_exact_integer_match"])
        self.assertFalse(row["quote_verified"])
        self.assertEqual(report["independently_validated_quote_samples"], 0)
        self.assertNotIn("cpmm_signed_output_matches_fee_model", row)
        self.assertFalse(report["broadcast"])

    @patch("arb.m5_three_venue_signed_quote_parity.accept", return_value=True)
    @patch("arb.m5_three_venue_signed_quote_parity.quote_cpmm_creator_fee_source",
           side_effect=ValueError("creator fee liabilities not authenticated"))
    def test_missing_creator_fee_state_blocks_without_trade_only_fallback(self, quote, _):
        report = compare(self.fixture, self.receipt, observed_unix=1)
        quote.assert_called_once()
        row = report["leg_comparisons"][0]
        self.assertIsNone(row["quoted_output_base_units"])
        self.assertIn("SOURCE_EXACT_QUOTE_BLOCKED", row["reason"])
        self.assertFalse(row["quote_verified"])
        self.assertEqual(report["independently_validated_quote_samples"], 0)
        self.assertEqual(report["blocked_leg_count"], 3)


if __name__ == "__main__":
    unittest.main()
