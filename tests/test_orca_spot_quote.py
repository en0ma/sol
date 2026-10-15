import unittest
from arb.orca_spot_quote import quote_single_tick,Q
class WhirlpoolSpotQuoteTests(unittest.TestCase):
    def state(self):
        return {"token_mint_a":"a","token_mint_b":"b",
                "liquidity":str(10**12),"sqrt_price_x64":str(Q),
                "fee_rate_hundredths_bps":3000}
    def test_both_directions_have_nonzero_indicative_outputs(self):
        for mint in ("a","b"):
            q=quote_single_tick(self.state(),mint,1000000)
            self.assertGreater(q["estimated_output_base_units"],0)
            self.assertFalse(q["actionable"])
            self.assertFalse(q["tick_boundary_verified"])
    def test_fee_and_mint_guards(self):
        with self.assertRaises(ValueError):quote_single_tick(self.state(),"other",1000)
        with self.assertRaises(ValueError):quote_single_tick(self.state(),"a",0)
        s=self.state();s["fee_rate_hundredths_bps"]=1000000
        with self.assertRaises(ValueError):quote_single_tick(s,"a",1000)
