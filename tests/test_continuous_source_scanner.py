"""A continuous scanner cannot upgrade topology to profitability or execution."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from arb.continuous_source_scanner import scan_once,run
from arb.m5_seven_venue_route_scan import ORDER

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
RPC="http://127.0.0.1:8899"


def fixture():
    pools={
        "orca":[("p-ab","A","B"),("p-ca","C","A")],
        "raydium_cpmm":[("p-bc","B","C")],
    }
    source={venue:[] for venue in ORDER}
    for venue,rows in pools.items():
        source[venue]=[{"venue":venue,"pool":address,"mints":[a,b],
                        "authenticated":True,"slot":100,**SAFE}
                       for address,a,b in rows]
    return {"source":"READ_ONLY_MAINNET_BACKED_SURFPOOL",
            "authenticated_pools":source,**SAFE}


def graph(*starts):
    return {"status":"SOURCE_AUTHENTICATED_ROUTE_DISCOVERY_ONLY",
            "routes":[{"hops":3,"start_mint":mint} for mint in starts],
            "cycle_coverage_by_hops":{"3":{"truncated":False}},**SAFE}


class ContinuousReadOnlyScannerTests(unittest.TestCase):
    def test_topology_not_profitability_or_signed_execution(self):
        with patch("arb.continuous_source_scanner.local_rpc_only"):
            report=scan_once(RPC,{"pools":[]},
                source_probe=lambda *_args,**_kw:fixture(),
                route_builder=lambda *_args,**_kw:graph("A","B"),
                target_unique_starts=200)
        self.assertEqual(report["source_topology_unique_start_mints"],3)
        self.assertEqual(report["selected_graph_unique_start_mints"],2)
        self.assertFalse(report["target_met_on_topology"])
        self.assertIsNone(report["profitable_routes"])
        self.assertIsNone(report["signed_rollback_verified_start_mints"])
        self.assertEqual(report["quoted_routes"],0)
        self.assertFalse(report["actionable"])
        self.assertFalse(report["broadcast"])

    def test_unverified_pool_and_non_topology_graph_start_fail_closed(self):
        with patch("arb.continuous_source_scanner.local_rpc_only"):
            with self.assertRaisesRegex(ValueError,"graph start"):
                scan_once(RPC,{"pools":[]},
                    source_probe=lambda *_args,**_kw:fixture(),
                    route_builder=lambda *_args,**_kw:graph("Z"))
            malformed=fixture()
            malformed["authenticated_pools"]["orca"][0]["authenticated"]=False
            with self.assertRaisesRegex(ValueError,"untrusted source"):
                scan_once(RPC,{"pools":[]},
                    source_probe=lambda *_args,**_kw:malformed,
                    route_builder=lambda *_args,**_kw:graph("A"))

    def test_failure_is_recorded_without_replaying_previous_success(self):
        calls=[]
        outcomes=[
            {"status":"READ_ONLY_COVERAGE_SCAN_NOT_PROFITABILITY_VERIFIED",
             "source_topology_unique_start_mints":3,**SAFE},
            ValueError("source fork unavailable")
        ]
        def scan(*_args,**_kwargs):
            item=outcomes.pop(0)
            if isinstance(item,Exception):
                raise item
            return item
        with tempfile.TemporaryDirectory() as directory:
            with patch("arb.continuous_source_scanner.local_rpc_only"):
                run(RPC,{"pools":[]},directory,max_scans=2,
                    interval_seconds=1,sleeper=calls.append,scan=scan)
            history=[json.loads(x) for x in
                     (Path(directory)/"history.jsonl").read_text().splitlines()]
            latest=json.loads((Path(directory)/"latest.json").read_text())
        self.assertEqual(len(history),2)
        self.assertEqual(calls,[1])
        self.assertEqual(latest["status"],"SOURCE_SCAN_FAILED")
        self.assertNotIn("source_topology_unique_start_mints",latest)
        self.assertIsNone(latest["profitable_routes"])
        self.assertFalse(latest["actionable"])

    def test_bad_schedule_rejected(self):
        with patch("arb.continuous_source_scanner.local_rpc_only"):
            with self.assertRaisesRegex(ValueError,"schedule"):
                run(RPC,{"pools":[]},"unused",interval_seconds=0,max_scans=1)


if __name__=="__main__":
    unittest.main()
