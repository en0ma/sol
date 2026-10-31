import base64,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from arb.m5_four_to_six_source_capture import capture
from arb.m5_source_indicative_route_chain import research_chain
from arb.m5_four_to_six_signed_handoff import assess

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
class ThreeMilestoneIntegrationTests(unittest.TestCase):
    def graph(self):
        m=["A","B","C","D","A"]
        venues=["orca","raydium_cpmm","raydium_clmm","raydium_amm_v4"]
        return {"status":"SOURCE_AUTHENTICATED_ROUTE_DISCOVERY_ONLY",
                "routes":[{"hops":4,"start_mint":"A","legs":[
                    {"venue":v,"pool":"P"+str(i),"input":m[i],"output":m[i+1]}
                    for i,v in enumerate(venues)]}],**SAFE}
    def test_real_four_hop_contextual_accounts_capture(self):
        graph=self.graph()
        venue_map={leg["venue"]:leg for leg in graph["routes"][0]["legs"]}
        by_raw={bytes([i+1]):leg for i,leg in enumerate(graph["routes"][0]["legs"])}
        def decoded(raw):
            leg=by_raw[raw]
            return {"token_mint_a":leg["input"],"token_mint_b":leg["output"],
                    "token_0_mint":leg["input"],"token_1_mint":leg["output"],
                    "token_mint_0":leg["input"],"token_mint_1":leg["output"],
                    "base_mint":leg["input"],"quote_mint":leg["output"]}
        programs={venue:"program-"+venue for venue in venue_map}
        account_values=[{"owner":programs[leg["venue"]],"executable":False,
                         "data":[base64.b64encode(bytes([i+1])).decode(),"base64"]}
                        for i,leg in enumerate(graph["routes"][0]["legs"])]
        decoders={v:decoded for v in venue_map}
        keys={v:("token_mint_a","token_mint_b") if v=="orca" else
              ("token_0_mint","token_1_mint") if v=="raydium_cpmm" else
              ("token_mint_0","token_mint_1") if v=="raydium_clmm" else
              ("base_mint","quote_mint") for v in venue_map}
        with tempfile.TemporaryDirectory() as d,patch(
             "arb.m5_four_to_six_source_capture.local_rpc_only"),patch(
             "arb.m5_four_to_six_source_capture.snapshot") as snap,patch(
             "arb.m5_four_to_six_source_capture.venue_accounts") as aux,patch(
             "arb.m5_four_to_six_source_capture.program_data_accounts",
             return_value={"EXECUTABLE":{"owner":"loader"}}),patch(
             "arb.m5_four_to_six_source_capture.call",
             return_value={"context":{"slot":42},"value":account_values}),patch(
             "arb.m5_four_to_six_source_capture.PROGRAMS",programs),patch(
             "arb.m5_four_to_six_source_capture.DECODERS",decoders),patch(
             "arb.m5_four_to_six_source_capture.MINT_KEYS",keys):
            snap.side_effect=lambda rpc,pool,venue: {"authenticated":True,"slot":42,
                "mints":[venue_map[venue]["input"],venue_map[venue]["output"]]}
            aux.side_effect=lambda rpc,venue,pool,mints:([pool],{})
            path=Path(d)/"four-hop.json"
            result=capture("http://127.0.0.1:8899",graph,0,path)
            import json
            fixture=json.loads(path.read_text())
            self.assertEqual(result["source_slot"],42)
            self.assertEqual(fixture["fixture_kind"],"AUTHENTICATED_FOUR_TO_SIX_HOP_SOURCE_ROUTE")
            self.assertEqual(fixture["state_account_count"],4)
            self.assertFalse(fixture["signed_atomic_simulation_verified"])
            self.assertFalse(result["broadcast"])
    @patch("arb.m5_source_indicative_route_chain.extract_pool_states")
    @patch("arb.m5_source_indicative_route_chain.quote_leg")
    def test_amount_aware_indicative_legs_never_claim_executable_net_profit(self,quote,states):
        states.return_value=[{"venue":v,"address":str(i),"mints":[a,b]} for i,(v,a,b) in
                             enumerate((("orca","A","B"),("raydium_cpmm","B","C"),("pumpswap","C","A")))]
        amounts=[]
        def adapter(fixture,*,leg_index,amount_in,observed_unix):
            amounts.append(amount_in)
            return {"quote_status":"SOURCE_BOUND_INDICATIVE",
                    "predicted_output_base_units":amount_in+1,"source_slot":42,**SAFE}
        quote.side_effect=adapter
        result=research_chain({"route_mints":["A","B","C","A"],"state_accounts_observed_slot":42,**SAFE},amount_in=100,observed_unix=20)
        self.assertEqual(amounts,[100,101,102])
        self.assertEqual(result["gross_delta_start_mint_base_units"],3)
        self.assertFalse(result["full_route_quoted"])
        self.assertFalse(result["net_profit_verified"])
        self.assertIsNone(result["net_delta_start_mint_base_units"])
        self.assertEqual(result["net_economics_status"],"UNCONVERTED_NETWORK_AND_PRIORITY_COSTS")
    @patch("arb.m5_source_indicative_route_chain.extract_pool_states")
    @patch("arb.m5_source_indicative_route_chain.quote_leg")
    def test_four_hop_native_amounts_are_chained_but_remain_indicative(self,quote,states):
        states.return_value=[{"venue":v,"address":str(i),"mints":[a,b]} for i,(v,a,b) in enumerate(
            (("orca","A","B"),("raydium_cpmm","B","C"),
             ("raydium_clmm","C","D"),("raydium_amm_v4","D","A")))]
        observed=[]
        def adapter(fixture,*,leg_index,amount_in,observed_unix):
            observed.append(amount_in)
            return {"quote_status":"SOURCE_BOUND_INDICATIVE",
                    "predicted_output_base_units":amount_in+2,"source_slot":42,**SAFE}
        quote.side_effect=adapter
        result=research_chain({"route_mints":["A","B","C","D","A"],
            "state_accounts_observed_slot":42,**SAFE},amount_in=100,observed_unix=20)
        self.assertEqual(observed,[100,102,104,106])
        self.assertEqual(result["output_base_units"],108)
        self.assertFalse(result["full_route_quoted"])
        self.assertFalse(result["signed_simulation_verified"])

    @patch("arb.m5_four_to_six_signed_handoff.verify")
    @patch("arb.m5_four_to_six_signed_handoff.extract_pool_states")
    def test_signed_handoff_must_not_accept_unverified_four_hop_claim(self,states,verify):
        states.return_value=[{"venue":"orca"} for _ in range(4)]
        fixture={"fixture_kind":"AUTHENTICATED_FOUR_TO_SIX_HOP_SOURCE_ROUTE",
                 "state_accounts_observed_slot":42,"route_pool_addresses":["a","b","c","d"],**SAFE}
        result=assess(fixture,quote_report={"source_quote_verified":True,
            "protocol_exact_verified":True,"snapshot_slot":42,"hops":4,**SAFE},
            signed_audit={"status":"VERIFIED_SIGNED_FOUR_TO_SIX_HOP_ROLLBACK",
              "signed_atomic_simulation_verified":True,
              "rollback_failure_case_verified":True,"route_pool_addresses":["a","b","c","d"],
              "snapshot_slot":42,**SAFE})
        self.assertFalse(result["independently_signed_verified"])
        self.assertIn("independent four-to-six-hop acceptance auditor not yet integrated",result["blockers"])
if __name__=="__main__":unittest.main()
