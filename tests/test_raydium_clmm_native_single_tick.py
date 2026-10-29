import unittest
from arb.raydium_clmm_native_single_tick import (
  sqrt_at_tick,quote_one_tick,evaluate,Q64)

def state(**kw):
    return {"sqrt_price_x64":str(Q64),"liquidity":"100000000000000",
        "tick_current":0,"fee_on":0,"dynamic_fee_info_nonzero":False,**kw}
def config(**kw):
    return {"trade_fee_rate":2500,**kw}

class RaydiumClmmNativeSingleTickTests(unittest.TestCase):
    def test_exact_onchain_sqrt_reference_constants(self):
        self.assertEqual(sqrt_at_tick(0),Q64)
        self.assertEqual(sqrt_at_tick(-1),0xfffcb933bd6fb800)
        self.assertEqual(sqrt_at_tick(1),((1<<128)-1)//0xfffcb933bd6fb800)
        self.assertLess(sqrt_at_tick(-60),Q64)
        self.assertGreater(sqrt_at_tick(60),Q64)
    def test_positive_outputs_on_both_sides_are_integer(self):
        # A price in the middle of a tick: one-tick bound holds for
        # small inputs. No float arithmetic is used in the source engine.
        p=(Q64+sqrt_at_tick(1))//2
        st=state(sqrt_price_x64=str(p))
        for direction in (True,False):
            q=quote_one_tick(st,config(),10000,zero_for_one=direction)
            self.assertGreater(q["output"],0)
            self.assertEqual(q["fee"],25)
            self.assertEqual(q["crossed_ticks"],0)
            self.assertFalse(q["official_sdk_parity_verified"])
    def test_crossing_tick_fails_closed(self):
        st=state(liquidity="10000")
        with self.assertRaisesRegex(ValueError,"crosses tick"):
            quote_one_tick(st,config(),10000,zero_for_one=True)
    def test_fee_consumes_input_rejected(self):
        with self.assertRaisesRegex(ValueError,"fee consumes"):
            quote_one_tick(state(),config(trade_fee_rate=999999),1,
                           zero_for_one=False)
    def test_dynamic_fee_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"dynamic fee"):
            quote_one_tick(state(dynamic_fee_info_nonzero=True),config(),
                           10000,zero_for_one=True)
    def test_fee_side_other_than_input_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"output-side"):
            quote_one_tick(state(fee_on=2),config(),10000,
                           zero_for_one=False)
    def test_no_source_cannot_claim_native_sdk_parity(self):
        with self.assertRaisesRegex(ValueError,"authenticated"):
            evaluate({"status":"UNVERIFIED","pools":[]})
    def test_input_validation_rejects_float_and_zero(self):
        for bad in (1.2,0,-4,2**64,True):
            with self.assertRaises(ValueError):
                quote_one_tick(state(),config(),bad,zero_for_one=True)

if __name__=="__main__":unittest.main()
