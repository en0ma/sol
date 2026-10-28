"""Ensure focused CI source dependencies match native-pricing acceptance."""
from pathlib import Path
import unittest

class SourceGraphCiOrderingTests(unittest.TestCase):
    def test_three_venue_source_handoff_precedes_signed_validation(self):
        workflow=Path(".github/workflows/amm-v4-focused.yml").read_text()
        capture=workflow.index("      - name: Reauthenticate registered Orca and Meteora identities")
        publish=workflow.index("          name: three-venue-authenticated-native-sources")
        shutdown=workflow.index("      - name: Shut down upstream-backed fork")
        offline=workflow.index("  offline-amm-v4:")
        download=workflow.index("      - name: Import authenticated three-venue source evidence")
        signed=workflow.index("      - name: Check new Orca pool pricing")
        self.assertLess(capture,publish)
        self.assertLess(publish,shutdown)
        self.assertLess(shutdown,offline)
        self.assertLess(offline,download)
        self.assertLess(download,signed)
        for obsolete in (
            "python3 -m arb.m5_seven_venue_route_scan",
            "python3 -m arb.m5_authenticated_multihop_shortlist",
            "python3 -m arb.m5_four_to_six_source_capture",
        ):
            self.assertNotIn(obsolete,workflow)

if __name__=="__main__":unittest.main()
