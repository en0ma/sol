"""DBC independent Q128 segment integer safety checks; not pool parity."""
import unittest
from arb.meteora_dbc_native_segment import (
    Q128, Q64, next_sqrt_from_exact_input, delta_base, delta_quote,
    quote_one_segment,
)


class DbcNativePrimitiveTests(unittest.TestCase):
    def test_base_input_price_moves_down(self):
        price=Q64
        liquidity=1<<96
        nxt=next_sqrt_from_exact_input(price,liquidity,1_000_000,True)
        self.assertLess(nxt,price)
        out=delta_quote(nxt,price,liquidity)
        self.assertGreater(out,0)

    def test_quote_input_price_moves_up(self):
        next_price=next_sqrt_from_exact_input(Q64,1<<96,100_000,False)
        self.assertGreater(next_price,Q64)

    def test_rounded_delta_monotonic(self):
        lower=Q64//2; upper=Q64
        liq=1<<96
        self.assertGreaterEqual(delta_base(lower,upper,liq,True),
                                delta_base(lower,upper,liq,False))
        self.assertGreaterEqual(delta_quote(lower,upper,liq,True),
                                delta_quote(lower,upper,liq,False))

    def test_crossing_rejected(self):
        with self.assertRaisesRegex(ValueError,"crossing"):
            quote_one_segment(sqrt_price=Q64,liquidity=1<<96,
                              input_amount=100_000,base_for_quote=True,
                              target_price=Q64-1)

    def test_no_signed_acceptance_in_native_curve(self):
        result=quote_one_segment(sqrt_price=Q128,liquidity=Q128*1_000_000_000,
                   input_amount=1_000_000,base_for_quote=True,
                   target_price=Q64//2)
        self.assertFalse(result["signed_verified"])
        self.assertFalse(result["full_pool_sdk_parity"])

    def test_zero_denominator_rejected(self):
        with self.assertRaisesRegex(ValueError,"invalid sqrt"):
            delta_base(0,Q64,1<<96)


if __name__=="__main__":unittest.main()
