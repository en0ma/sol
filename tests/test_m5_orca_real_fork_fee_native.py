"""Reproduce measured Orca terminal SPL deltas from an actual signed Surfpool trial.

Source: authenticated fork source fixture slot 462282629; Orca pool
27ZbVdmoUhG639CfqG6kW8a4VXZeGBi8Dd4HUXjVDxeS. Input sizes and outputs
are read from independent signed-size-*.json receipt artifact #12783652654.
The fee-reference clock is a controlled scenario; current-fork CI checks actual
receipt identity and fresh source state separately.
"""
import unittest
from arb.orca_adaptive_fee_source import quote_adaptive_from_arrays

class OrcaObservedForkAdaptiveFeeParity(unittest.TestCase):
    def state(self):
        return {"token_mint_a":"So11111111111111111111111111111111111111112",
                "token_mint_b":"4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
                "liquidity":"6946168988",
                "sqrt_price_x64":"4414893978626378945",
                "tick_current_index":-28600,"tick_spacing":4,
                "fee_rate_hundredths_bps":400}
    def oracle(self):
        return {"pool":"27ZbVdmoUhG639CfqG6kW8a4VXZeGBi8Dd4HUXjVDxeS",
                "oracle_layout_authenticated":True,
                "constants":{"filter_period":30,"decay_period":600,
                    "reduction_factor":5000,
                    "adaptive_fee_control_factor":60000,
                    "max_volatility_accumulator":880000,
                    "tick_group_size":4,"major_swap_threshold_ticks":4},
                "variables":{"last_reference_update_timestamp":1793149154,
                    "last_major_swap_timestamp":1793149154,
                    "volatility_reference":21442,
                    "tick_group_index_reference":-7154,
                    "volatility_accumulator":31442},
                "effective_adaptive_fee_math_verified":False,
                "actionable":False,"broadcast":False,"live_execution_approved":False}
    def arrays(self):
        return [{"start_tick":start,"ticks":[],"status":"DYNAMIC_VALID"}
                for start in (-28864,-29216,-29568)]
    def test_real_three_size_fork_outputs_with_decay_window(self):
        # Verify the archived swap outputs, not invented token amounts.
        for input_amount,observed_output in (
                (173573,9937),(1735834,99376),(17358368,993167)):
            with self.subTest(input_amount=input_amount):
                q=quote_adaptive_from_arrays(
                    self.state(),self.state()["token_mint_a"],input_amount,
                    self.arrays(),self.oracle(),observed_unix=1793149190)
                self.assertEqual(q["estimated_output_base_units"],observed_output)
                self.assertTrue(q["source_oracle_decoded"])
                self.assertFalse(q["signed_source_quote_exact_verified"])
                self.assertFalse(q["broadcast"])

    def test_no_oracle_or_wrong_fork_time_rejected(self):
        with self.assertRaisesRegex(ValueError,"Oracle reference"):
            quote_adaptive_from_arrays(
                self.state(),self.state()["token_mint_a"],173573,
                self.arrays(),self.oracle(),observed_unix=1793149000)
        with self.assertRaisesRegex(ValueError,"authenticated adaptive"):
            quote_adaptive_from_arrays(
                self.state(),self.state()["token_mint_a"],173573,
                self.arrays(),{},observed_unix=1793149190)
    def test_missing_initialized_array_coverage_rejected(self):
        with self.assertRaisesRegex(ValueError,"current tick array"):
            quote_adaptive_from_arrays(
                self.state(),self.state()["token_mint_a"],173573,
                [{"start_tick":-29216,"ticks":[],"status":"DYNAMIC_VALID"}],
                self.oracle(),observed_unix=1793149190)
