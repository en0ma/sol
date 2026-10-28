import unittest
from arb.pumpswap_native_candidate import quote_exact_input, fee, SOL, ZERO


def fixture():
    return {
        "verified":True,"canonical_pool_verified":True,"canonical":True,
        "base_mint":"B"*32,"quote_mint":SOL,"coin_creator":ZERO,
        "creator_fee_bps":0,"is_mayhem_mode":0,"is_cashback_coin":0,
        "base_mint_supply":1_000_000,
        "base_reserve":100_000,"quote_vault_balance":200_000,
        "virtual_quote_reserves":-10_000,
        "protocol_fees_accrued":5_000,"creator_fees_accrued":1_000,
        "fee_config":{"account_authenticated":True,"fee_tiers":[{
            "market_cap_threshold":0,
            "fees":{"lp_fee_bps":100,"protocol_fee_bps":50,"creator_fee_bps":25}
        }],"flat_fees":{"lp_fee_bps":10,"protocol_fee_bps":20,"creator_fee_bps":0}},
        "global_config":{"buy_enabled":True,"sell_enabled":True}
    }


class PumpSwapNativeCandidateTest(unittest.TestCase):
    def test_component_fees_ceil_individually(self):
        self.assertEqual(fee(1,1),1)
        self.assertEqual(fee(0,1),0)
        self.assertEqual(fee(10000,1),1)

    def test_buy_exact_quote_in_matches_reference_integer_order(self):
        p=fixture()
        r=quote_exact_input(p,SOL,10000)
        # coin creator is zero so creator fee is suppressed; 150bps total.
        net=10000*10000//10150
        charge=(net*100+9999)//10000+(net*50+9999)//10000
        net-=max(0,net+charge-10000)
        expected=p["base_reserve"]*(net-1)//(190000+net-1)
        self.assertEqual(r["native_formula_candidate_out"],expected)
        self.assertFalse(r["signed_parity_verified"])
        self.assertFalse(r["actionable"])

    def test_sell_respects_signed_virtual_and_fee_buckets(self):
        p=fixture()
        r=quote_exact_input(p,p["base_mint"],1000)
        gross=190000*1000//101000
        expected=gross-(gross*100+9999)//10000-(gross*50+9999)//10000
        self.assertEqual(r["native_formula_candidate_out"],expected)

    def test_cashback_or_unverified_oversight_fails_closed(self):
        p=fixture();p["is_cashback_coin"]=1
        with self.assertRaisesRegex(ValueError,"cashback"):
            quote_exact_input(p,SOL,1000)
        p=fixture();p["fee_config"]["account_authenticated"]=False
        with self.assertRaisesRegex(ValueError,"authenticated"):
            quote_exact_input(p,SOL,1000)
        p=fixture();p["creator_fee_bps"]=30
        with self.assertRaisesRegex(ValueError,"creator fee gate"):
            quote_exact_input(p,SOL,1000)

    def test_spendable_liquidity_is_not_virtual_reserve(self):
        p=fixture();p["protocol_fees_accrued"]=199999
        with self.assertRaisesRegex(ValueError,"invalid PumpSwap physical"):
            quote_exact_input(p,p["base_mint"],1000)

    def test_missing_authenticated_pool_flags_fails(self):
        p=fixture();p.pop("is_cashback_coin")
        with self.assertRaisesRegex(ValueError,"cashback status"):
            quote_exact_input(p,SOL,1000)


if __name__=="__main__":
    unittest.main()
