"""Validate CI source-graph prerequisite ordering without network dependencies."""
from pathlib import Path
import unittest

class SourceGraphCiOrderingTests(unittest.TestCase):
    def test_shortlist_runs_after_graph_producer_before_fork_shutdown(self):
        workflow=Path(".github/workflows/amm-v4-focused.yml").read_text()
        start=workflow.index("      - name: Enumerate broad untrusted all-seven market pool hints")
        assess=workflow.index("      - name: Validate authenticated source graph connectivity")
        shortlist=workflow.index("      - name: Prioritize source-authenticated four-to-six-hop venue-diverse research leads")
        shutdown=workflow.index("      - name: Shut down upstream-backed fork before offline account writes")
        self.assertLess(start,assess)
        self.assertLess(assess,shortlist)
        self.assertLess(shortlist,shutdown)
        self.assertIn("python3 -m arb.m5_seven_venue_route_scan",workflow[start:assess])
        self.assertIn("m5-broad-source-route-candidates.json",workflow[start:assess])
        self.assertEqual(workflow.count("      - name: Enumerate broad untrusted all-seven market pool hints"),1)
        self.assertEqual(workflow.count("      - name: Prioritize source-authenticated four-to-six-hop venue-diverse research leads"),1)
        self.assertIn("m5-authenticated-multihop-shortlist.json",workflow[shortlist:shutdown])
if __name__=="__main__":unittest.main()
