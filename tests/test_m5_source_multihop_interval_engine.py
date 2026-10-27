import unittest
from unittest.mock import patch
from arb.m5_source_multihop_interval_engine import walk
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
class MultihopSourceIntervalTests(unittest.TestCase):
    def fixture(self):
        return {"route_mints":["A","B","C","D","A"],
                "state_accounts_observed_slot":43,**SAFE}
    def rows(self):
        return [{"venue":v,"address":"pool"+str(i),"mints":[a,b],
                 "snapshot_slot":43} for i,(v,a,b) in enumerate([
            ("orca","A","B"),("meteora_dlmm","B","C"),
            ("meteora_damm_v2","C","D"),("pumpswap","D","A")])]
    @patch("arb.m5_source_multihop_interval_engine.quote_leg")
    @patch("arb.m5_source_multihop_interval_engine.extract_pool_states")
    def test_mixed_dlmm_damm_pump_ranges_propagate_not_promote(self,states,quote):
        states.return_value=self.rows()
        def native(f,*,leg_index,amount_in,observed_unix):
            base={"venue":self.rows()[leg_index]["venue"],"pool":"pool"+str(leg_index),
                  "source_slot":43,**SAFE}
            if leg_index==0:
                return {**base,"quote_status":"SOURCE_BOUND_INDICATIVE",
                        "predicted_output_base_units":amount_in+10}
            if leg_index==2:
                return {**base,"quote_status":"NATIVE_QUOTE_MODELED_NOT_EXACT",
                    "native_fee_envelope":{"status":"DAMM_V2_SOURCE_RESERVE_HYPOTHETICAL_FEE_ENVELOPE",
                        "source_slot":43,"lower_modeled_output":amount_in-3,
                        "upper_modeled_output":amount_in-1,**SAFE}}
            if leg_index==3:
                return {**base,"quote_status":"NATIVE_QUOTE_MODELED_NOT_EXACT",
                    "native_fee_envelope":{"status":"PUMPSWAP_SOURCE_FEE_TIER_SCENARIOS_NOT_EXHAUSTIVE",
                        "source_slot":43,"minimum_candidate_output":amount_in-2,
                        "maximum_candidate_output":amount_in+1,**SAFE}}
            return {**base,"quote_status":"NATIVE_QUOTE_BOUNDED_NOT_EXACT",
                    "native_fee_envelope":{"source_slot":43,
                        "lower_output_bound":amount_in-2,
                        "upper_output_bound":amount_in+1,**SAFE}}
        quote.side_effect=native
        r=walk(self.fixture(),input_base_units=100,observed_unix=123)
        self.assertEqual(r["route_hops"],4)
        self.assertGreater(r["minimum_modeled_output"],0)
        self.assertTrue(r["hypothetical_fee_model_present"])
        self.assertTrue(r["scenario_envelope_not_true_interval"])
        self.assertFalse(r["full_route_quote_verified"])
        self.assertFalse(r["net_profit_verified"])
        self.assertFalse(r["broadcast"])
    @patch("arb.m5_source_multihop_interval_engine.quote_leg")
    @patch("arb.m5_source_multihop_interval_engine.extract_pool_states")
    def test_unsafe_bound_cannot_escape(self,states,quote):
        states.return_value=self.rows()
        quote.return_value={"venue":"orca","pool":"pool0","source_slot":43,
            "quote_status":"NATIVE_QUOTE_BOUNDED_NOT_EXACT",
            "native_fee_envelope":{"source_slot":43,"lower_output_bound":1,
                                    "upper_output_bound":2,
                                    **{**SAFE,"broadcast":True}},**SAFE}
        with self.assertRaisesRegex(ValueError,"unsafe"):
            walk(self.fixture(),input_base_units=100,observed_unix=123)
if __name__=="__main__":unittest.main()
