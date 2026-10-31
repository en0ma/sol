import unittest
from unittest.mock import patch
from arb.m5_source_trade_size_sweep import sweep

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
class MultiSizeTests(unittest.TestCase):
    @patch("arb.m5_source_trade_size_sweep.evaluate")
    def test_exposes_cross_size_quote_and_blocker_counts(self,ev):
        def fake(source_dir,*,amount_in,observed_unix,maximum):
            return {"native_fully_quoted":1,"native_quote_blocked":2,
                "positive_gross_indicative":1,"ranked_routes":[{
                  "source_batch_route_index":7,"start_mint":"A",
                  "gross_delta_start_mint_base_units":amount_in//10}],**SAFE}
        ev.side_effect=fake
        out=sweep("/source",sizes=[100,200,300],observed_unix=123)
        self.assertEqual(out["total_native_fully_quoted"],3)
        self.assertEqual(out["total_native_quote_blocked"],6)
        self.assertEqual(out["total_positive_gross_indicative"],3)
        self.assertEqual(out["gross_positive_shortlist"][0]["amount_in_base_units"],300)
        self.assertEqual(out["gross_positive_shortlist"][0]["source_batch_route_index"],7)
        self.assertEqual(out["net_profitable_opportunities_verified"],0)
        self.assertFalse(out["broadcast"])
    def test_invalid_and_duplicate_trade_sizes_fail_closed(self):
        for sizes in ([],[100,100],[0],[True],list(range(1,10))):
            with self.subTest(sizes=sizes),self.assertRaises(ValueError):
                sweep("/source",sizes=sizes,observed_unix=123)
    @patch("arb.m5_source_trade_size_sweep.evaluate")
    def test_no_real_quote_outputs_zero_not_fabricated(self,ev):
        ev.return_value={"native_fully_quoted":0,"native_quote_blocked":4,
            "positive_gross_indicative":0,"ranked_routes":[]}
        out=sweep("/source",sizes=[100],observed_unix=123)
        self.assertEqual(out["gross_positive_shortlist"],[])
        self.assertEqual(out["total_native_quote_blocked"],4)
if __name__=="__main__":unittest.main()
