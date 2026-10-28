import unittest
from arb.raydium_clmm_cross_tick_quote import (
    Q,DEN,ceil_div,quote_across_initialized_ticks)
from arb.orca_tick_math import sqrt_price_from_tick_index
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}

class RaydiumCrossTickSourceNativeTests(unittest.TestCase):
    def pool(self):
        return {"token_mint_0":"mint0","token_mint_1":"mint1",
            "sqrt_price_x64":sqrt_price_from_tick_index(0),
            "liquidity":10_000_000_000,"tick_current":0}
    def ticks(self):
        return [{"tick_index":i,"liquidity_net":net,"liquidity_gross":100_000_000_000}
                for i,net in ((-30,0),(-20,-100_000_000),(-10,100_000_000),
                              (0,0),(10,100_000_000),(20,-100_000_000),
                              (30,0))]
    def test_zero_for_one_small_input_no_cross_and_exact_conservation(self):
        result=quote_across_initialized_ticks(
            self.pool(),"mint0",1000,2500,self.ticks())
        self.assertEqual(result["amount_in"],1000)
        self.assertEqual(sum(x["gross_input_base_units"] for x in result["steps"]),1000)
        self.assertEqual(sum(x["fee_input_base_units"] for x in result["steps"]),
                         result["fee_input_base_units"])
        self.assertGreater(result["amount_out"],0)
        self.assertFalse(result["protocol_exact_verified"])
        self.assertFalse(result["broadcast"])
    def test_zero_for_one_crosses_real_initialized_liquidity_and_reprices(self):
        result=quote_across_initialized_ticks(
            self.pool(),"mint0",8_000_000,2500,self.ticks())
        self.assertGreaterEqual(result["crossed_ticks"],2)
        self.assertEqual(result["crossed_source_liquidity"][0]["tick_index"],0)
        self.assertEqual(result["crossed_source_liquidity"][1]["tick_index"],-10)
        self.assertEqual(result["crossed_source_liquidity"][1]["liquidity_after_crossing"],
                         9_900_000_000)
        self.assertEqual(sum(x["gross_input_base_units"] for x in result["steps"]),
                         8_000_000)
    def test_one_for_zero_crosses_upward_and_adds_net_liquidity(self):
        result=quote_across_initialized_ticks(
            self.pool(),"mint1",8_000_000,2500,self.ticks())
        self.assertGreater(result["crossed_ticks"],0)
        self.assertEqual(result["crossed_source_liquidity"][0]["tick_index"],10)
        self.assertEqual(result["crossed_source_liquidity"][0]["liquidity_after_crossing"],
                         10_100_000_000)
    def test_tick_inventory_exhaustion_is_failure_not_a_partial_quote(self):
        small=[row for row in self.ticks() if row["tick_index"] in (0,-10)]
        with self.assertRaisesRegex(ValueError,"initialized tick missing"):
            quote_across_initialized_ticks(self.pool(),"mint0",
                500_000_000,2500,small)
    def test_rejects_forged_crossing_liquidity(self):
        ticks=self.ticks()
        ticks[3]["liquidity_net"]=ticks[3]["liquidity_gross"]+1
        with self.assertRaisesRegex(ValueError,"liquidity"):
            quote_across_initialized_ticks(self.pool(),"mint0",100,2500,ticks)
    def test_rejects_duplicate_source_tick(self):
        with self.assertRaisesRegex(ValueError,"uniqueness"):
            quote_across_initialized_ticks(self.pool(),"mint0",100,2500,
                self.ticks()+[self.ticks()[0]])
    def test_oversized_crossing_budget_blocks(self):
        with self.assertRaisesRegex(ValueError,"crossing budget"):
            quote_across_initialized_ticks(self.pool(),"mint0",8_000_000,2500,
                self.ticks(),max_crossings=0)
    def test_unobserved_intermediate_tick_array_cannot_be_skipped(self):
        state=self.pool()
        state["tick_spacing"]=1
        state["authenticated_tick_array_starts"]=[0,-120]
        source=[{"tick_index":0,"liquidity_net":0,
                 "liquidity_gross":10_000_000_000},
                {"tick_index":-121,"liquidity_net":0,
                 "liquidity_gross":10_000_000_000}]
        with self.assertRaisesRegex(ValueError,"unobserved gap"):
            quote_across_initialized_ticks(state,"mint0",100_000_000,
                2500,source)
    def test_missing_current_array_fails_before_quote(self):
        state=self.pool()
        state["tick_spacing"]=1
        state["authenticated_tick_array_starts"]=[-60]
        with self.assertRaisesRegex(ValueError,"active tick array"):
            quote_across_initialized_ticks(state,"mint0",1000,
                2500,self.ticks())
    def test_nonzero_fee_and_input_conservation(self):
        result=quote_across_initialized_ticks(self.pool(),"mint1",
            3_000_000,12000,self.ticks())
        self.assertGreater(result["fee_input_base_units"],0)
        self.assertEqual(sum(s["gross_input_base_units"] for s in result["steps"]),3_000_000)
        self.assertTrue(all(s["gross_input_base_units"]==
            s["net_input_base_units"]+s["fee_input_base_units"] for s in result["steps"]))
if __name__=="__main__":unittest.main()

class RaydiumFeeOnOutputResearchModels(RaydiumCrossTickSourceNativeTests):
    def test_fee_on_output_deducts_from_output_not_input(self):
        for mint in ("mint0","mint1"):
            with self.subTest(mint=mint):
                modeled=quote_across_initialized_ticks(
                    self.pool(),mint,100000,2500,self.ticks(),fee_on_input=False)
                self.assertEqual(modeled["amount_in"],100000)
                self.assertEqual(modeled["fee_input_base_units"],0)
                self.assertGreater(modeled["fee_output_base_units"],0)
                self.assertEqual(sum(step["fee_output_base_units"]
                    for step in modeled["steps"]),modeled["fee_output_base_units"])
                self.assertEqual(modeled["fee_collection_mode"],"OUTPUT")
                self.assertFalse(modeled["source_fee_collection_mode_verified"])
                self.assertFalse(modeled["protocol_exact_verified"])

    def test_fee_on_output_zero_fee_equals_input_fee_mode(self):
        for mint in ("mint0","mint1"):
            base=quote_across_initialized_ticks(
                self.pool(),mint,100000,0,self.ticks(),fee_on_input=True)
            alt=quote_across_initialized_ticks(
                self.pool(),mint,100000,0,self.ticks(),fee_on_input=False)
            self.assertEqual(base["amount_out"],alt["amount_out"])
            self.assertEqual(alt["fee_output_base_units"],0)

    def test_invalid_unattested_fee_mode_refused(self):
        with self.assertRaisesRegex(ValueError,"fee collection mode"):
            quote_across_initialized_ticks(
                self.pool(),"mint0",1000,2500,self.ticks(),fee_on_input="output")
