"""SDK OnlyY fee-mode and modeled-chain regressions (not live evidence)."""
import unittest
from unittest.mock import patch
from arb.meteora_dlmm_bin_quote import Q, quote_bins
from arb.meteora_dlmm_source_fee_decoder import dynamic_fee_rate_by_bin
from arb.meteora_dlmm import SIZE, DISC
from arb.m5_source_indicative_route_chain import research_chain, SAFE


class OutputFeeTests(unittest.TestCase):
    def test_output_fee_partial_fill(self):
        b=[{"bin_id":0,"amount_x":0,"amount_y":1000,"price_q64":2*Q}]
        out=quote_bins(amount_in=101,swap_x_for_y=True,bins=b,
                       total_fee_rate=10000000,fee_on_input=False)
        self.assertEqual(out["amount_out"],199)
        self.assertEqual(out["fee_output_base_units"],3)
        self.assertEqual(out["fee_input_base_units"],0)

    def test_output_fee_exhaustion_rounds_per_bin(self):
        bins=[{"bin_id":0,"amount_x":0,"amount_y":5,"price_q64":3*Q},
              {"bin_id":-1,"amount_x":0,"amount_y":100,"price_q64":Q}]
        out=quote_bins(amount_in=12,swap_x_for_y=True,bins=bins,
                       total_fee_rate=100000000,fee_on_input=False)
        self.assertEqual(out["amount_out"],13)
        self.assertEqual(out["fee_output_base_units"],2)
        self.assertEqual(out["bins_traversed"][0]["gross_input_base_units"],2)
        self.assertEqual(out["bins_traversed"][0]["gross_output_base_units"],5)
        self.assertFalse(out["protocol_exact_verified"])

    def test_fee_mode_requires_explicit_direction(self):
        raw=bytearray(SIZE);raw[:8]=DISC;raw[36]=1
        args=dict(bin_step=25,observed_unix=10,active_bin_id=0,visited_bin_ids=[0])
        with self.assertRaisesRegex(ValueError,"output-denominated"):
            dynamic_fee_rate_by_bin(bytes(raw),swap_x_for_y=True,**args)
        output=dynamic_fee_rate_by_bin(bytes(raw),swap_x_for_y=True,
                                      allow_output_fee=True,**args)
        self.assertFalse(output["fee_on_input"])
        self.assertTrue(dynamic_fee_rate_by_bin(bytes(raw),swap_x_for_y=False,
                                      allow_output_fee=True,**args)["fee_on_input"])


class ModeledRouteTests(unittest.TestCase):
    def test_model_requires_opt_in_and_binds_actual_chained_input(self):
        fixture={"route_mints":["A","B","A"],"state_accounts_observed_slot":10,**SAFE}
        rows=[{"venue":"meteora_dlmm","address":"p","mints":["A","B"]},
              {"venue":"raydium_cpmm","address":"q","mints":["A","B"]}]
        model={"status":"SOURCE_VOLATILITY_DYNAMIC_FEE_MODELED","source_clock":20,
               "amount_out":92,"protocol_exact_verified":False,**SAFE}
        first={"venue":"meteora_dlmm","pool":"p","source_slot":10,
               "quote_status":"NATIVE_QUOTE_SOURCE_DERIVED_NOT_EXACT",
               "native_fee_envelope":{"pool":"p","input_mint":"A","output_mint":"B",
                "input_base_units":100,"source_slot":10,"source_derived_dynamic_fee_quote":model},**SAFE}
        second={"venue":"raydium_cpmm","pool":"q","source_slot":10,
                "quote_status":"SOURCE_BOUND_INDICATIVE","predicted_output_base_units":98,**SAFE}
        with patch("arb.m5_source_indicative_route_chain.extract_pool_states",return_value=rows), \
             patch("arb.m5_source_indicative_route_chain.quote_leg",side_effect=[first,first,second]) as quote:
            self.assertEqual(research_chain(fixture,amount_in=100,observed_unix=20)["status"],
                             "NATIVE_ROUTE_INDICATIVE_BLOCKED")
            r=research_chain(fixture,amount_in=100,observed_unix=20,allow_modeled_dlmm=True)
            self.assertEqual(quote.call_args.kwargs["amount_in"],92)
        self.assertTrue(r["modeled_all_legs"])
        self.assertFalse(r["indicative_all_legs"])
        self.assertFalse(r["full_route_quoted"])
        self.assertEqual(r["gross_delta_start_mint_base_units"],-2)
        self.assertFalse(r["net_profit_verified"])


if __name__=="__main__":
    unittest.main()
