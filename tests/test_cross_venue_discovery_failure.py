import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from arb.cross_venue_discovery import main
from arb.rpc import RPCError

class DiscoveryFailureTests(unittest.TestCase):
    @patch("arb.cross_venue_discovery.pinned_fallback")
    @patch("arb.cross_venue_discovery.discover_and_simulate")
    def test_upstream_rate_limit_produces_explicit_artifact(self, discover, fallback):
        fallback.side_effect = RPCError("429 Too Many Requests")
        discover.side_effect = RPCError("429 Too Many Requests")
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "discovery.json")
            with patch.dict("os.environ", {"CROSS_VENUE_DISCOVERY_REPORT": path}):
                self.assertEqual(main(), 2)
            report = json.loads(Path(path).read_text())
            self.assertEqual(report["status"], "DISCOVERY_BLOCKED_UPSTREAM_RATE_LIMIT")
            self.assertFalse(report["pool_counts_verified"])
            self.assertFalse(report["actionable"])
            self.assertEqual(report["routes"], [])

    @patch("arb.cross_venue_discovery.discover_and_simulate")
    def test_success_writes_verified_report(self, discover):
        discover.return_value = {"status": "BOUNDED_DISCOVERY_COMPLETE",
                                 "broadcast": False, "routes": []}
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "discovery.json")
            with patch.dict("os.environ", {"CROSS_VENUE_DISCOVERY_REPORT": path}):
                self.assertEqual(main(), 0)
            self.assertEqual(json.loads(Path(path).read_text())["status"],
                             "BOUNDED_DISCOVERY_COMPLETE")

