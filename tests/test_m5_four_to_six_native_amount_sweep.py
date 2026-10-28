import unittest
from unittest.mock import patch
from arb.m5_four_to_six_native_amount_sweep import sweep

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
class FourToSixNativeSweepTests(unittest.TestCase):
    def fixture(self):
        return {"state_accounts_observed_slot":42,**SAFE}
    def rows(self):
        return [{"venue":v,"address":"pool"+str(i),"mints":[a,b]} for i,(v,a,b) in enumerate((
            ("orca","A","B"),("meteora_dlmm","B","C"),
            ("pumpswap","C","D"),("raydium_amm_v4","D","A")))]
    @patch("arb.m5_four_to_six_native_amount_sweep.walk")
    @patch("arb.m5_four_to_six_native_amount_sweep.research_chain")
    @patch("arb.m5_four_to_six_native_amount_sweep.quote_leg")
    @patch("arb.m5_four_to_six_native_amount_sweep.extract_pool_states")
    def test_probes_all_four_real_venue_adapters_when_first_leg_blocks(self,states,quote,chain,walk):
        states.return_value=self.rows()
        walk.return_value={"status":"MULTIHOP_NATIVE_SOURCE_INTERVAL_BLOCKED"}
        chain.return_value={"status":"NATIVE_ROUTE_INDICATIVE_BLOCKED",
                            "blocked_leg_index":0,"blocked_venue":"orca","quoted_legs":[]}
        quote.return_value={"quote_status":"NATIVE_QUOTE_BLOCKED",
                            "reason":"MISSING_NATIVE_AUXILIARY_STATE",**SAFE}
        r=sweep(self.fixture(),observed_unix=123,amounts=(100,1000))
        self.assertEqual(r["attempt_count"],2)
        self.assertEqual(r["venue_probe_count"],8)
        self.assertEqual({x["venue"] for x in r["venue_probes"]},
                         {"orca","meteora_dlmm","pumpswap","raydium_amm_v4"})
        self.assertEqual(quote.call_count,8)
        self.assertEqual(r["complete_indicative_chain_count"],0)
        self.assertEqual(r["indicative_ranked_input_sizes"],[])
        self.assertEqual(r["protocol_exact_route_count"],0)
        self.assertEqual(r["net_profitable_route_count"],0)
        self.assertFalse(r["broadcast"])
    @patch("arb.m5_four_to_six_native_amount_sweep.walk")
    @patch("arb.m5_four_to_six_native_amount_sweep.research_chain")
    @patch("arb.m5_four_to_six_native_amount_sweep.quote_leg")
    @patch("arb.m5_four_to_six_native_amount_sweep.extract_pool_states")
    def test_unsafe_native_leg_fails_closed(self,states,quote,chain,walk):
        states.return_value=self.rows()
        chain.return_value={"status":"NATIVE_ROUTE_INDICATIVE_BLOCKED","quoted_legs":[]}
        walk.return_value={"status":"MULTIHOP_NATIVE_SOURCE_INTERVAL_BLOCKED"}
        quote.return_value={"quote_status":"SOURCE_BOUND_INDICATIVE",
                            **{**SAFE,"broadcast":True}}
        with self.assertRaisesRegex(ValueError,"unsafe"):
            sweep(self.fixture(),observed_unix=123,amounts=(100,))
    @patch("arb.m5_four_to_six_native_amount_sweep.extract_pool_states")
    def test_live_source_fixture_rejected(self,states):
        states.return_value=self.rows()
        with self.assertRaises(ValueError):
            sweep({**self.fixture(),"actionable":True},observed_unix=123)

if __name__=="__main__":unittest.main()

class AuthenticatedScenarioChainTests(FourToSixNativeSweepTests):
    def scenario(self):
        values=[100,90,80,70,60]
        trace=[]
        for i,row in enumerate(self.rows()):
            trace.append({"leg_index":i,"venue":row["venue"],
                "pool":row["address"],"source_slot":42,
                "amount_in":values[i],"amount_out":values[i+1],
                "quote_status":"SOURCE_BOUND_INDICATIVE"})
        return {"status":"MULTIHOP_SOURCE_SCENARIO_INTERVAL_NOT_EXACT",
                "completed_branches":[{"amount":60,"trace":trace,
                    "hypothetical":False,"source_bounded":True}]}
    @patch("arb.m5_four_to_six_native_amount_sweep.walk")
    @patch("arb.m5_four_to_six_native_amount_sweep.research_chain")
    @patch("arb.m5_four_to_six_native_amount_sweep.quote_leg")
    @patch("arb.m5_four_to_six_native_amount_sweep.extract_pool_states")
    def test_every_venue_receives_observed_previous_leg_amount(self,states,quote,chain,walk):
        states.return_value=self.rows()
        chain.return_value={"status":"NATIVE_ROUTE_INDICATIVE_BLOCKED","quoted_legs":[]}
        quote.return_value={"quote_status":"NATIVE_QUOTE_BLOCKED",**SAFE}
        walk.return_value=self.scenario()
        report=sweep(self.fixture(),observed_unix=123,amounts=(100,))
        self.assertEqual(report["chained_venue_probe_count"],4)
        self.assertEqual([r["exact_input_base_units"] for r in report["chained_venue_probes"]],
                         [100,90,80,70])
        self.assertEqual(report["modeled_scenario_candidate_count"],1)
        self.assertFalse(report["modeled_scenario_ranking_not_profitable"][0]["net_profit_verified"])

    @patch("arb.m5_four_to_six_native_amount_sweep.walk")
    @patch("arb.m5_four_to_six_native_amount_sweep.research_chain")
    @patch("arb.m5_four_to_six_native_amount_sweep.extract_pool_states")
    def test_tampered_intermediate_source_amount_is_rejected(self,states,chain,walk):
        states.return_value=self.rows()
        chain.return_value={"status":"NATIVE_ROUTE_INDICATIVE_BLOCKED","quoted_legs":[]}
        fake=self.scenario()
        fake["completed_branches"][0]["trace"][2]["amount_in"]=999
        walk.return_value=fake
        with self.assertRaisesRegex(ValueError,"unbound"):
            sweep(self.fixture(),observed_unix=123,amounts=(100,))
