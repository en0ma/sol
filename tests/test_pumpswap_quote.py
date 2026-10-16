import unittest
from arb.pumpswap_quote import quote_exact_input


class PumpSwapQuoteTests(unittest.TestCase):
    def pool(self):
        return {"venue":"pumpswap","verified":True,"fee_verified_onchain":True,
                "effective_fee_verified":True,
                "global_config":{"effective_fee_verified":True,
                                 "buy_enabled":True,"sell_enabled":True},
                "base_mint":"BASE","quote_mint":"QUOTE",
                "base_reserve":1000000,"quote_vault_balance":2000000,
                "virtual_quote_reserves":-250000,
                "protocol_fees_accrued":100000,"creator_fees_accrued":50000}

    def test_both_directions_and_fee_effect(self):
        pool=self.pool()
        sell=quote_exact_input(pool,"BASE",10000,verified_total_fee_ppm=10000)
        buy=quote_exact_input(pool,"QUOTE",10000,verified_total_fee_ppm=10000)
        self.assertEqual(sell["mint_out"],"QUOTE")
        self.assertEqual(buy["mint_out"],"BASE")
        self.assertEqual(sell["effective_quote_reserve"],1750000)
        self.assertEqual(sell["spendable_quote_reserve"],1850000)
        self.assertGreater(sell["estimated_output_base_units"],0)
        self.assertGreater(buy["estimated_output_base_units"],0)
        self.assertFalse(sell["executable_quote"])
        nofee=quote_exact_input(pool,"BASE",10000,verified_total_fee_ppm=0)
        self.assertLess(sell["estimated_output_base_units"],
                        nofee["estimated_output_base_units"])

    def test_fee_or_account_state_absent_fails_closed(self):
        pool=self.pool()
        pool["fee_verified_onchain"]=False
        with self.assertRaises(ValueError):
            quote_exact_input(pool,"BASE",10000,verified_total_fee_ppm=10000)
        pool=self.pool()
        del pool["virtual_quote_reserves"]
        with self.assertRaises(ValueError):
            quote_exact_input(pool,"BASE",10000,verified_total_fee_ppm=10000)

    def test_fee_buckets_and_signed_virtual_reserve(self):
        pool=self.pool()
        pool["virtual_quote_reserves"]=-3000000
        with self.assertRaisesRegex(ValueError,"effective"):
            quote_exact_input(pool,"BASE",10000,verified_total_fee_ppm=10000)
        pool=self.pool()
        pool["protocol_fees_accrued"]=2000001
        with self.assertRaisesRegex(ValueError,"accrued"):
            quote_exact_input(pool,"BASE",10000,verified_total_fee_ppm=10000)

    def test_insufficient_physical_liquidity_blocks_sell(self):
        pool=self.pool()
        pool.update(quote_vault_balance=200000,
                    virtual_quote_reserves=2000000,
                    protocol_fees_accrued=199999,
                    creator_fees_accrued=0)
        with self.assertRaisesRegex(ValueError,"spendable"):
            quote_exact_input(pool,"BASE",100000,verified_total_fee_ppm=10000)

    def test_missing_dynamic_fee_evidence_blocks_quote(self):
        pool=self.pool()
        pool["effective_fee_verified"]=False
        with self.assertRaisesRegex(ValueError,"dynamic fee"):
            quote_exact_input(pool,"BASE",10000,verified_total_fee_ppm=10000)
        pool=self.pool()
        pool["global_config"]["effective_fee_verified"]=False
        with self.assertRaisesRegex(ValueError,"evidence missing"):
            quote_exact_input(pool,"BASE",10000,verified_total_fee_ppm=10000)

    def test_disabled_swap_direction_blocks_quote(self):
        pool=self.pool()
        pool["global_config"]["sell_enabled"]=False
        with self.assertRaisesRegex(ValueError,"direction disabled"):
            quote_exact_input(pool,"BASE",10000,verified_total_fee_ppm=10000)
        pool=self.pool()
        pool["global_config"]["buy_enabled"]=False
        with self.assertRaisesRegex(ValueError,"direction disabled"):
            quote_exact_input(pool,"QUOTE",10000,verified_total_fee_ppm=10000)
