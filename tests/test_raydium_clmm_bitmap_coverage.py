"""Minimized constants from actual BZ6-02 source slot 474836231.
Captured pool 3Sht4Amox5REC1YLYGuR1Qdfh7fa8d2ucGu4rawjs6tN;
archive experiment 46112159892. This is arithmetic replay, not fresh execution.
"""
import unittest
from arb.raydium_clmm_cross_tick_quote import quote_across_initialized_ticks

class BitmapCoverageTests(unittest.TestCase):
    def setUp(self):
        self.starts=[1800,-207600,15600,104400]
        self.state={"token_mint_0":"SOL","token_mint_1":"NEET","tick_spacing":10,
                    "tick_current":13035,"liquidity":452154552701,
                    "sqrt_price_x64":35396763588736437148,
                    "authenticated_tick_array_starts":self.starts}
        self.ticks=[{"tick_index":i,"liquidity_net":n,"liquidity_gross":abs(n)}
                    for i,n in ((2010,5273803428),(-207260,120527599590),
                                (15880,-5273803428),(104880,-120527599590))]
        self.bitmap=sum(1<<(start//600+512) for start in self.starts)
    def quote(self,amount,bitmap=None,state=None,ticks=None):
        return quote_across_initialized_ticks(state or self.state,"SOL",amount,1000,
                    self.ticks if ticks is None else ticks,
                    default_bitmap_bytes=(self.bitmap if bitmap is None else bitmap).to_bytes(128,"little"))
    def test_actual_signed_small_and_large_sample(self):
        for amount,output in ((100000,367834),(1000000,3678335)):
            result=self.quote(amount)
            self.assertEqual(result["amount_out"],output)
            self.assertIn(12600,result["bitmap_proven_empty_array_starts"])
            self.assertEqual(result["crossed_ticks"],0)
            self.assertFalse(result["protocol_exact_verified"])
    def test_missing_initialized_active_array_fails(self):
        with self.assertRaisesRegex(ValueError,"active initialized array missing"):
            self.quote(100000,bitmap=self.bitmap|(1<<(12600//600+512)))
    def test_missing_intervening_initialized_array_fails(self):
        with self.assertRaisesRegex(ValueError,"initialized array missing across"):
            self.quote(100000,bitmap=self.bitmap|(1<<(12000//600+512)))
    def test_captured_array_bitmap_contradiction_fails(self):
        with self.assertRaisesRegex(ValueError,"contradicts source bitmap"):
            self.quote(100000,bitmap=self.bitmap&~(1<<(1800//600+512)))
    def test_without_bitmap_original_gate_remains(self):
        with self.assertRaisesRegex(ValueError,"active tick array missing"):
            quote_across_initialized_ticks(self.state,"SOL",100000,1000,self.ticks)

if __name__=="__main__":unittest.main()
