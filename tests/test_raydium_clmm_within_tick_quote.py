import unittest
from arb.raydium_clmm_within_tick_quote import quote_within_tick,Q


class RaydiumClmmWithinTickQuoteTests(unittest.TestCase):
    def setUp(self):
        self.pool={"token_mint_0":"SOL","token_mint_1":"USDC",
                   "sqrt_price_x64":Q,"liquidity":10000000000}

    def test_two_directions_are_indicative(self):
        for mint,bound in (("SOL",Q-Q//20),("USDC",Q+Q//20)):
            with self.subTest(mint=mint):
                quote=quote_within_tick(self.pool,mint,100000,3000,bound)
                self.assertGreater(quote["estimated_output_base_units"],0)
                self.assertFalse(quote["executable_quote"])
                self.assertFalse(quote["actionable"])
                self.assertEqual(quote["crossed_ticks"],0)

    def test_boundary_crossing_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"crosses"):
            quote_within_tick(self.pool,"SOL",100000,3000,Q-1)

    def test_unauthenticated_fee_type_rejected(self):
        with self.assertRaisesRegex(ValueError,"authenticated"):
            quote_within_tick(self.pool,"SOL",100000,True,Q-Q//20)

    def test_dust_and_wrong_mint_rejected(self):
        with self.assertRaises(ValueError):
            quote_within_tick(self.pool,"SOL",1,999999,Q-Q//20)
        with self.assertRaisesRegex(ValueError,"mint"):
            quote_within_tick(self.pool,"FAKE",100000,3000,Q-Q//20)
