import unittest
from arb.pumpswap_fee_tiers import select_fee_tier


class PumpSwapFeeTierTests(unittest.TestCase):
    def config(self):
        return {"flat_fees":{"lp_fee_bps":20,"protocol_fee_bps":10,"creator_fee_bps":10},
                "fee_tiers":[
                    {"market_cap_threshold":100,
                     "fees":{"lp_fee_bps":100,"protocol_fee_bps":50,"creator_fee_bps":20}},
                    {"market_cap_threshold":1000,
                     "fees":{"lp_fee_bps":75,"protocol_fee_bps":25,"creator_fee_bps":10}}]}

    def choose(self, canonical, quote_reserve):
        return select_fee_tier(self.config(),canonical=canonical,
            base_mint_supply=1000,base_reserve=1000,
            quote_reserve=quote_reserve)

    def test_canonical_market_cap_threshold_boundaries(self):
        for market_cap,expected in ((99,100),(100,100),(999,100),(1000,75)):
            with self.subTest(market_cap=market_cap):
                self.assertEqual(self.choose(True,market_cap)["fee_rates"]["lp_fee_bps"],expected)
        self.assertFalse(self.choose(True,1000)["source_verified"])

    def test_noncanonical_uses_flat_fees_not_market_cap(self):
        out=self.choose(False,10000000)
        self.assertEqual(out["fee_rates"]["lp_fee_bps"],20)
        self.assertEqual(out["selection"],"NONCANONICAL_FLAT")

    def test_missing_fee_tiers_and_bad_data_rejected(self):
        cfg=self.config()
        cfg["fee_tiers"]=[]
        with self.assertRaises(ValueError):
            select_fee_tier(cfg,canonical=True,base_mint_supply=1,
                            base_reserve=1,quote_reserve=1)
        cfg=self.config()
        cfg["fee_tiers"][1]["market_cap_threshold"]=100
        with self.assertRaises(ValueError):
            select_fee_tier(cfg,canonical=True,base_mint_supply=1,
                            base_reserve=1,quote_reserve=1)
        with self.assertRaises(ValueError):
            select_fee_tier(self.config(),canonical=True,base_mint_supply=0,
                            base_reserve=1,quote_reserve=1)
