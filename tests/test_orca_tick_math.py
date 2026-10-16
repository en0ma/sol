import unittest
from arb.orca_tick_math import (
    Q, MAX_TICK, MIN_SQRT, MAX_SQRT, sqrt_price_from_tick_index,
)


class OrcaTickMathTests(unittest.TestCase):
    def test_canonical_extrema_and_zero(self):
        self.assertEqual(sqrt_price_from_tick_index(0), Q)
        self.assertEqual(sqrt_price_from_tick_index(-MAX_TICK), MIN_SQRT)
        self.assertEqual(sqrt_price_from_tick_index(MAX_TICK), MAX_SQRT)

    def test_tick_price_is_strictly_monotone(self):
        for tick in (-443635, -10000, -1024, -1, 0, 1, 1024, 10000, 443635):
            with self.subTest(tick=tick):
                self.assertLess(sqrt_price_from_tick_index(tick-1),
                                sqrt_price_from_tick_index(tick))
                self.assertLess(sqrt_price_from_tick_index(tick),
                                sqrt_price_from_tick_index(tick+1))

    def test_out_of_bounds_and_boolean_rejected(self):
        for tick in (-MAX_TICK-1, MAX_TICK+1, True, 1.0):
            with self.assertRaises(ValueError):
                sqrt_price_from_tick_index(tick)

    def test_reference_math_wired_into_decoded_array_bridge(self):
        from arb.orca_multitick_quote import quote_from_decoded_arrays
        state = {'token_mint_a':'a', 'token_mint_b':'b',
                 'sqrt_price_x64':str(Q), 'liquidity':str(10**12),
                 'fee_rate_hundredths_bps':3000,
                 'tick_spacing':1, 'tick_current_index':0}
        arrays=[{'start_tick':0,'status':'FIXED_VALID',
                 'ticks':[{'tick_index':10, 'liquidity_net':'0'}]}]
        quote=quote_from_decoded_arrays(state,'b',10000,arrays)
        self.assertEqual(quote['ticks_crossed'],0)
        self.assertEqual(quote['source'],'SUPPLIED_ARRAYS_AND_REFERENCE_TICK_MATH')
        self.assertFalse(quote['actionable'])
        self.assertFalse(quote['executable_quote'])
