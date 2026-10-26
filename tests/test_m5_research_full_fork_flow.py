"""End-to-end M5 control-plane tests: real source engine wiring, no trade claims."""
import os
import unittest
from unittest.mock import patch
from arb.m5_seven_venue_route_scan import run_m5_research, ORDER, SAFE


def readiness():
    pools={v:[] for v in ORDER}
    for venue,pool in (("orca","p-o"),("raydium_cpmm","p-c"),
                       ("raydium_amm_v4","p-v")):
        pools[venue].append({"venue":venue,"pool":pool,"mints":["A","B"],
            "slot":9,"authenticated":True,**SAFE})
    return {"source":"READ_ONLY_MAINNET_BACKED_SURFPOOL",
            "authenticated_pools":pools,"failed_pool_checks":[],**SAFE}


class M5EndToEndResearch(unittest.TestCase):
    @patch("arb.m5_seven_venue_route_scan.probe")
    @patch("arb.m5_seven_venue_route_scan.local_rpc_only")
    def test_read_only_stage_never_invents_quotes_or_signatures(self,local,probe):
        probe.return_value=readiness()
        report=run_m5_research("http://127.0.0.1:8899",{"pools":[]})
        self.assertGreater(report["connected_cycles"],0)
        self.assertEqual(report["quoted_candidates"],0)
        self.assertEqual(report["signed_simulation_attempts"],0)
        self.assertEqual(report["source_triangles"]["status"],"NOT_REQUESTED")
        self.assertFalse(report["broadcast"])
        self.assertEqual(probe.call_count,1)

    @patch("arb.m5_distinct_venue_coverage_batch.offline_batch")
    @patch("arb.m5_distinct_venue_coverage_batch.source_batch")
    @patch("arb.m5_seven_venue_route_scan.probe")
    @patch("arb.m5_seven_venue_route_scan.local_rpc_only")
    def test_existing_exporter_and_signed_batch_are_reused(self,local,probe,source,signed):
        probe.return_value=readiness()
        source.return_value={"attempted":2,"exported":2,"routes":[]}
        signed.return_value={"attempted":2,"independent_signed_accepted":1,
            "independently_validated_quote_samples":0,"routes":[]}
        with patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"1"}):
            report=run_m5_research("http://127.0.0.1:8899",{"pools":[]},
                source_dir="/tmp/source",signed_dir="/tmp/signed",
                observed_unix=123,maximum=2)
        self.assertEqual(report["signed_triangle_source_attempts"],2)
        self.assertEqual(report["signed_simulation_attempts"],2)
        self.assertEqual(report["independently_signed_triangles_accepted"],1)
        self.assertEqual(report["ranked_profitable_candidates"],0)
        self.assertEqual(report["protocol_exact_quote_samples"],0)
        self.assertFalse(report["broadcast"])
        source.assert_called_once()
        signed.assert_called_once_with("http://127.0.0.1:8899",
            "/tmp/source","/tmp/signed",observed_unix=123)

    @patch("arb.m5_seven_venue_route_scan.probe")
    @patch("arb.m5_seven_venue_route_scan.local_rpc_only")
    def test_missing_explicit_fork_gate_blocks_before_source_export(self,local,probe):
        with patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"0"}):
            with self.assertRaises(ValueError):
                run_m5_research("http://127.0.0.1:8899",{"pools":[]},
                                source_dir="/tmp/fixtures")
        probe.assert_not_called()

    @patch("arb.m5_seven_venue_route_scan.probe")
    @patch("arb.m5_seven_venue_route_scan.local_rpc_only")
    def test_signed_mode_requires_source_and_observed_time(self,local,probe):
        with patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"1"}):
            for kwargs in ({"signed_dir":"/tmp/signed"},
                           {"source_dir":"/tmp/source","signed_dir":"/tmp/signed"},
                           {"source_dir":"/tmp/source","signed_dir":"/tmp/signed",
                            "observed_unix":-1}):
                with self.subTest(kwargs=kwargs):
                    with self.assertRaises(ValueError):
                        run_m5_research("http://127.0.0.1:8899",{"pools":[]},
                                        **kwargs)
        probe.assert_not_called()

    @patch("arb.m5_distinct_venue_coverage_batch.offline_batch")
    @patch("arb.m5_source_triangle_quote_ranking.rank")
    @patch("arb.m5_distinct_venue_coverage_batch.source_batch")
    @patch("arb.m5_seven_venue_route_scan.probe")
    @patch("arb.m5_seven_venue_route_scan.local_rpc_only")
    def test_only_quote_ranked_positive_routes_enter_real_signed_runner(
            self,local,probe,source,rank,signed):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import json
        probe.return_value=readiness()
        source.return_value={"attempted":2,"exported":2,"routes":[
            {"index":0,"status":"AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE",
             "fixture":"triangle-00.json"},
            {"index":1,"status":"AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE",
             "fixture":"triangle-01.json"}]}
        rank.return_value={"fully_quoted":2,"positive_gross":1,
            "ranked":[{"index":1,"positive_gross":True}],
            "all_results":[{"index":0},{"index":1}]}
        signed.return_value={"attempted":1,"independent_signed_accepted":0,
                             "independently_validated_quote_samples":0}
        with TemporaryDirectory() as temp, patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"1"}):
            for i in range(2):
                (Path(temp)/("triangle-%02d.json"%i)).write_text(json.dumps({"fixture":i}))
            report=run_m5_research("http://127.0.0.1:8899",{"pools":[]},
                source_dir=temp,signed_dir="/tmp/m5-signed",observed_unix=100,
                quote_input=1000)
        self.assertEqual(report["signed_selection"]["selected_source_route_indices"],[1])
        self.assertEqual(report["signed_simulation_attempts"],1)
        self.assertEqual(report["quoted_candidates"],2)
        self.assertEqual(report["ranked_profitable_candidates"],0)
        self.assertFalse(report["broadcast"])
        self.assertEqual(signed.call_args.kwargs["route_indices"],[1])

    @patch("arb.m5_distinct_venue_coverage_batch.offline_batch")
    @patch("arb.m5_source_triangle_quote_ranking.rank")
    @patch("arb.m5_distinct_venue_coverage_batch.source_batch")
    @patch("arb.m5_seven_venue_route_scan.probe")
    @patch("arb.m5_seven_venue_route_scan.local_rpc_only")
    def test_no_positive_gross_route_means_zero_signed_attempts(
            self,local,probe,source,rank,signed):
        probe.return_value=readiness()
        source.return_value={"attempted":0,"exported":0,"routes":[]}
        rank.return_value={"fully_quoted":0,"positive_gross":0,
            "ranked":[],"all_results":[]}
        signed.return_value={"attempted":0,"independent_signed_accepted":0,
                             "independently_validated_quote_samples":0}
        with patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"1"}):
            report=run_m5_research("http://127.0.0.1:8899",{"pools":[]},
                source_dir="/tmp/unused",signed_dir="/tmp/m5-signed",
                observed_unix=100,quote_input=1000)
        self.assertEqual(report["signed_selection"]["selected_source_route_indices"],[])
        self.assertEqual(report["signed_simulation_attempts"],0)
        self.assertEqual(signed.call_args.kwargs["route_indices"],[])


if __name__=="__main__":
    unittest.main()
