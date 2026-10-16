import unittest
from arb.orca_multitick_quote import Q, quote_multitick


class MultitickIndicativeTests(unittest.TestCase):
    def state(self):
        return {'token_mint_a': 'a', 'token_mint_b': 'b',
                'sqrt_price_x64': str(Q), 'liquidity': str(1000000000000),
                'fee_rate_hundredths_bps': 3000}

    def test_cross_and_partially_consume_next_tick_both_directions(self):
        for mint, target, net in [('a', Q - 1000000000000, 10000000000),
                                  ('b', Q + 1000000000000, -10000000000)]:
            with self.subTest(mint=mint):
                ticks = [{'tick_index': 10, 'sqrt_price_x64': target, 'liquidity_net': net},
                         {'tick_index': 20, 'sqrt_price_x64': target - 100000000000000 if mint == 'a' else target + 100000000000000, 'liquidity_net': 0}]
                q = quote_multitick(self.state(), mint, 1000000, ticks)
                self.assertEqual(q['ticks_crossed'], 1)
                self.assertEqual(q['steps'][0]['kind'], 'cross')
                self.assertEqual(q['steps'][1]['kind'], 'partial')
                self.assertGreater(q['estimated_output_base_units'], 0)
                self.assertFalse(q['actionable'])
                self.assertFalse(q['executable_quote'])

    def test_missing_tick_coverage_rejected(self):
        with self.assertRaisesRegex(ValueError, 'missing tick coverage'):
            quote_multitick(self.state(), 'b', 1000000,
                            [{'tick_index': 1, 'sqrt_price_x64': Q + 1000000000000, 'liquidity_net': 0}])

    def test_bad_order_and_liquidity_rejected(self):
        with self.assertRaises(ValueError):
            quote_multitick(self.state(), 'a', 100000,
                            [{'tick_index': 1, 'sqrt_price_x64': Q + 1, 'liquidity_net': 0}])
        with self.assertRaises(ValueError):
            quote_multitick(self.state(), 'b', 1000000,
                            [{'tick_index': 1, 'sqrt_price_x64': Q + 1000000000000,
                              'liquidity_net': -(10**12)}])

    def test_crossing_budget(self):
        with self.assertRaisesRegex(ValueError, 'crossing budget'):
            quote_multitick(self.state(), 'a', 1000000,
                            [{'tick_index': 1, 'sqrt_price_x64': Q - 1000000000000,
                              'liquidity_net': 0}], max_crossings=0)
