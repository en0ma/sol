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


if __name__=="__main__":
    unittest.main()
