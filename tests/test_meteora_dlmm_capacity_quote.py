"""Native bin exhaustion rounding; observed constants from run 46076493040.

These are minimized integer regressions from captured state, not a fresh
source fixture or independent signed receipt. SDK reference:
MeteoraAg/dlmm-sdk commons/src/extensions/bin.rs get_max_amount_in/swap,
commons/src/extensions/lb_pair.rs compute_fee/compute_fee_from_amount.
"""
import unittest
from arb.meteora_dlmm_bin_quote import quote_bins, Q


def captured_bins():
    return [
        {"bin_id": -200, "amount_x": 1629, "amount_y": 715354322,
         "price_q64": 351467660127173608, "effective_fee_rate": 10000000},
        {"bin_id": -199, "amount_x": 36809117407, "amount_y": 0,
         "price_q64": 358497013329717080, "effective_fee_rate": 10300000},
    ]


class DlmmCapacityRoundingTests(unittest.TestCase):
    def test_captured_y_to_x_cross_bin_samples(self):
        for amount, expected in ((1923, 97851), (100000, 5092509)):
            with self.subTest(amount=amount):
                report = quote_bins(amount_in=amount, swap_x_for_y=False,
                    bins=captured_bins(), total_fee_rate=10000000)
                self.assertEqual(report["amount_out"], expected)
                self.assertEqual(report["bins_traversed"][0]["gross_input_base_units"], 33)
                self.assertEqual(report["bins_traversed"][0]["output_base_units"], 1629)
                self.assertFalse(report["protocol_exact_verified"])

    def test_both_directions_ceiling_capacity_and_fee(self):
        for direction, price in ((True, 3*Q), (False, Q//3)):
            with self.subTest(direction=direction):
                bins = [{"bin_id": 0, "amount_x": 5, "amount_y": 5, "price_q64": price},
                        {"bin_id": -1 if direction else 1,
                         "amount_x": 100, "amount_y": 100, "price_q64": Q}]
                report = quote_bins(amount_in=8, swap_x_for_y=direction, bins=bins,
                    total_fee_rate=100000000)
                first = report["bins_traversed"][0]
                self.assertEqual(first["gross_input_base_units"], 3)
                self.assertEqual(first["output_base_units"], 5)
                self.assertEqual(first["fee_input_base_units"], 1)
                self.assertEqual(report["amount_out"], 9)

    def test_exact_capacity_and_partial_input(self):
        for amount, expected in ((32, 1627), (33, 1629)):
            report = quote_bins(amount_in=amount, swap_x_for_y=False,
                bins=captured_bins(), total_fee_rate=10000000)
            self.assertEqual(report["amount_out"], expected)
            self.assertEqual(len(report["bins_traversed"]), 1)

    def test_empty_zero_price_bin_is_skipped(self):
        bins = [{"bin_id": 0, "amount_x": 0, "amount_y": 0, "price_q64": 0},
                {"bin_id": 1, "amount_x": 100, "amount_y": 0, "price_q64": Q}]
        self.assertEqual(quote_bins(amount_in=10, swap_x_for_y=False, bins=bins,
            total_fee_rate=0)["amount_out"], 10)

    def test_capacity_plateau_does_not_overconsume(self):
        bins = [{"bin_id": 0, "amount_x": 0, "amount_y": 1, "price_q64": Q//4},
                {"bin_id": -1, "amount_x": 0, "amount_y": 100, "price_q64": Q}]
        report = quote_bins(amount_in=10, swap_x_for_y=True, bins=bins, total_fee_rate=0)
        self.assertEqual(report["bins_traversed"][0]["gross_input_base_units"], 4)
        self.assertEqual(report["amount_out"], 7)

    def test_insufficient_inventory_is_not_partial_fill(self):
        with self.assertRaisesRegex(ValueError, "cannot fill"):
            quote_bins(amount_in=100, swap_x_for_y=False,
                bins=captured_bins()[:1], total_fee_rate=10000000)


if __name__ == "__main__":
    unittest.main()
