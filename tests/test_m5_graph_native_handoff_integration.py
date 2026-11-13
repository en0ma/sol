"""Integration controls for graph-selected 4..6-hop native research."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from arb.m5_seven_venue_route_scan import run_m5_research, SAFE

def graph():
    return {"status":"SOURCE_AUTHENTICATED_ROUTE_DISCOVERY_ONLY",
            "routes":[{"hops":4,"start_mint":"A","legs":[]},
                      {"hops":5,"start_mint":"A","legs":[]}],
            "signed_simulation_attempts":0,**SAFE}

def captured(rpc, report, index, output):
    if index == 0:
        raise ValueError("stale first source")
    Path(output).write_text(json.dumps({"fixture_kind":"TEST_SOURCE"}))
    return {"status":"AUTHENTICATED_FOUR_TO_SIX_HOP_SOURCE_FIXTURE",
            "source_slot":42,**SAFE}

class GraphNativeIntegration(unittest.TestCase):
    @patch("arb.m5_source_indicative_route_chain.research_chain")
    @patch("arb.m5_four_to_six_signed_handoff.assess")
    @patch("arb.m5_four_to_six_source_capture.capture",side_effect=captured)
    @patch("arb.m5_distinct_venue_coverage_batch.source_batch")
    @patch("arb.m5_seven_venue_route_scan.analyze",side_effect=lambda *a,**k:graph())
    @patch("arb.m5_seven_venue_route_scan.probe",return_value={"authenticated_pools":{}})
    @patch("arb.m5_seven_venue_route_scan.local_rpc_only")
    def test_graph_fixture_native_chain_handoff_without_false_signing(
        self,local,probe,analyze,source_batch,capture,assess,chain):
        source_batch.return_value={"attempted":0,"exported":0,"routes":[]}
        chain.return_value={"status":"NATIVE_ROUTE_INDICATIVE_BLOCKED",
                            "blocked_leg_index":2,**SAFE}
        assess.return_value={"status":"FOUR_TO_SIX_HOP_SIGNED_HANDOFF_BLOCKED",
                             "signed_handoff_ready":False,**SAFE}
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"graph-fixture.json"
            with patch.dict("os.environ",{"SURFPOOL_EXPLICITLY_OFFLINE":"1"}):
                result=run_m5_research("http://127.0.0.1:8899",{},
                    source_dir=str(Path(root)/"source"),quote_input=100,
                    observed_unix=99,four_to_six_source_output=str(path))
            self.assertEqual(result["four_to_six_source_fixture"]["graph_route_index"],1)
            self.assertEqual(result["four_to_six_source_fixture"]["candidate_capture_attempts"],2)
            self.assertEqual(result["four_to_six_native_quote_chain"]["blocked_leg_index"],2)
            self.assertTrue((Path(root)/"graph-fixture-native-chain.json").is_file())
            self.assertFalse(result["four_to_six_signed_handoff"]["signed_handoff_ready"])
            self.assertEqual(result["signed_simulation_attempts"],0)
            self.assertFalse(result["broadcast"])
            chain.assert_called_once()
            self.assertEqual(chain.call_args.kwargs["amount_in"],100)

    @patch("arb.m5_four_to_six_source_capture.capture",side_effect=ValueError("no state"))
    @patch("arb.m5_distinct_venue_coverage_batch.source_batch")
    @patch("arb.m5_seven_venue_route_scan.analyze",side_effect=lambda *a,**k:graph())
    @patch("arb.m5_seven_venue_route_scan.probe",return_value={"authenticated_pools":{}})
    @patch("arb.m5_seven_venue_route_scan.local_rpc_only")
    def test_missing_graph_source_never_implies_a_signed_receipt(
        self,local,probe,analyze,source_batch,capture):
        source_batch.return_value={"attempted":0,"exported":0,"routes":[]}
        with tempfile.TemporaryDirectory() as root:
            with patch.dict("os.environ",{"SURFPOOL_EXPLICITLY_OFFLINE":"1"}):
                result=run_m5_research("http://127.0.0.1:8899",{},
                    source_dir=str(Path(root)/"source"),quote_input=100,
                    observed_unix=99,
                    four_to_six_source_output=str(Path(root)/"source.json"))
            self.assertEqual(result["four_to_six_source_fixture"]["candidate_capture_attempts"],2)
            self.assertEqual(result["four_to_six_native_quote_chain"]["status"],"NOT_REQUESTED")
            self.assertEqual(result["signed_simulation_attempts"],0)
            self.assertFalse(result["broadcast"])

if __name__=="__main__":
    unittest.main()
