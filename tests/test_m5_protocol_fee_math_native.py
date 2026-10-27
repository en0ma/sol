import unittest
from unittest.mock import patch
from arb.meteora_damm_v2_native_fee_math import (
    quote_native_fee,time_scheduler_numerator,FEE_DENOMINATOR)
from arb.pumpswap_source_tier_selector import (
    market_cap_quote_base_units,choose_tier_by_source_market_cap,
    mint_decimals_from_account,USDC)
from arb.pumpswap_pool import NATIVE_WSOL_MINT
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}

class NativeDAMMFeeMathTests(unittest.TestCase):
    def test_fee_denominator_is_native_billion(self):
        self.assertEqual(FEE_DENOMINATOR,1000000000)
        buy=quote_native_fee(reserve_a=1000000,reserve_b=1000000,
            amount_in=10000,input_is_a=True,total_fee_numerator=10000000,
            collection_mode="BASE_AND_QUOTE",fee_version=1)
        sell=quote_native_fee(reserve_a=1000000,reserve_b=1000000,
            amount_in=10000,input_is_a=False,total_fee_numerator=10000000,
            collection_mode="QUOTE_ONLY",fee_version=1)
        self.assertGreater(buy["fee_output_units"],0)
        self.assertEqual(buy["fee_input_units"],0)
        self.assertGreater(sell["fee_input_units"],0)
        self.assertEqual(sell["fee_output_units"],0)
        self.assertFalse(buy["protocol_exact_verified"])
    def test_fee_version_ceiling(self):
        with self.assertRaisesRegex(ValueError,"ceiling"):
            quote_native_fee(reserve_a=100,reserve_b=100,amount_in=10,
                input_is_a=True,total_fee_numerator=600000000,
                collection_mode="BASE_AND_QUOTE",fee_version=0)
    def test_time_scheduler_boundary_and_reduction(self):
        linear=time_scheduler_numerator(cliff_fee_numerator=100000000,
            number_of_periods=3,period_frequency=10,reduction_factor=10000000,
            elapsed=25,mode="linear")
        self.assertEqual(linear["fee_numerator"],80000000)
        self.assertEqual(linear["periods_elapsed"],2)
        exponential=time_scheduler_numerator(cliff_fee_numerator=100000000,
            number_of_periods=3,period_frequency=10,reduction_factor=100000000,
            elapsed=25,mode="exponential")
        self.assertEqual(exponential["fee_numerator"],81000000)

class PumpSourceTierSelectionTests(unittest.TestCase):
    def test_quote_denomination_is_human_billion_tokens(self):
        result=market_cap_quote_base_units(base_reserve=1000_000000,
            quote_reserve=2000_000000,virtual_quote_reserves=-200_000000,
            base_decimals=6)
        self.assertEqual(result["market_cap_quote_base_units"],1_800_000_000_000_000)
    def test_initialized_classic_mint_decimals(self):
        raw=bytearray(82)
        raw[44]=6
        raw[45]=1
        self.assertEqual(mint_decimals_from_account(bytes(raw)),6)
        with self.assertRaises(ValueError):
            mint_decimals_from_account(bytes(raw[:-1]))
    @patch("arb.pumpswap_source_tier_selector.classify_pool")
    def test_canonical_usdc_tier_derived_from_authenticated_thresholds(self,canonical):
        canonical.return_value={"canonical":True}
        config={"account_authenticated":True,"stable_fee_tiers":[
            {"market_cap_threshold":0,"fees":{"lp_fee_bps":20,"protocol_fee_bps":50,"creator_fee_bps":30}},
            {"market_cap_threshold":1500_000000,"fees":{"lp_fee_bps":40,"protocol_fee_bps":50,"creator_fee_bps":20}}],
            "fee_tiers":[]}
        state={"base_mint":"base","quote_mint":USDC,
            "virtual_quote_reserves":0,"is_mayhem_mode":0,"is_cashback_coin":0}
        result=choose_tier_by_source_market_cap(pool_state=state,
            fee_config=config,base_reserve=1000000000,
            quote_reserve=2000000000,base_decimals=0,
            base_supply_base_units=1_000_000_000)
        self.assertTrue(result["tier_selected"])
        self.assertEqual(result["selected_threshold_quote_base_units"],1500_000000)
        self.assertEqual(result["selected_total_fee_bps"],110)
        self.assertFalse(result["protocol_exact_verified"])
    @patch("arb.pumpswap_source_tier_selector.classify_pool")
    def test_cashback_mode_rejected_as_unresolved(self,canonical):
        canonical.return_value={"canonical":True}
        result=choose_tier_by_source_market_cap(pool_state={"base_mint":"base",
            "quote_mint":NATIVE_WSOL_MINT,"is_mayhem_mode":0,
            "is_cashback_coin":1},fee_config={"account_authenticated":True},
            base_reserve=100,quote_reserve=100,base_decimals=6,
            base_supply_base_units=1_000_000_000)
        self.assertFalse(result["tier_selected"])
    def test_market_cap_rejects_virtual_liquidity_underflow(self):
        with self.assertRaisesRegex(ValueError,"nonpositive"):
            market_cap_quote_base_units(base_reserve=100,quote_reserve=100,
                virtual_quote_reserves=-200,base_decimals=6)
if __name__=="__main__":unittest.main()
