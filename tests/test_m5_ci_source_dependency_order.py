"""Ensure focused CI source dependencies match native-pricing acceptance."""
from pathlib import Path
import unittest

class SourceGraphCiOrderingTests(unittest.TestCase):
    def test_each_venue_has_explicit_authenticated_capture_and_signed_stage(self):
        workflow=Path(".github/workflows/amm-v4-focused.yml").read_text()
        stages=(
            ("Authenticate registered Orca Whirlpool and Meteora DAMM v2 pools",
             "Capture authenticated Orca Whirlpool pricing source accounts",
             "Verify registered Orca Whirlpool native pricing against signed Surfpool"),
            ("Authenticate registered Orca Whirlpool and Meteora DAMM v2 pools",
             "Capture authenticated Meteora DAMM v2 pricing source accounts",
             "Verify registered Meteora DAMM v2 native pricing against signed Surfpool"),
            ("Authenticate registered Raydium CPMM pools",
             "Capture authenticated Raydium CPMM pricing source accounts",
             "Verify registered Raydium CPMM native pricing against signed Surfpool"),
        )
        for auth,capture,signed in stages:
            with self.subTest(capture=capture):
                a=workflow.index("      - name: "+auth)
                c=workflow.index("      - name: "+capture)
                v=workflow.index("      - name: "+signed)
                self.assertLess(a,c)
                self.assertLess(c,v)
                self.assertEqual(workflow.count("      - name: "+capture),1)

    def test_three_venue_source_handoff_precedes_signed_validation(self):
        workflow=Path(".github/workflows/amm-v4-focused.yml").read_text()
        capture=workflow.index("      - name: Authenticate registered Orca Whirlpool and Meteora DAMM v2 pools")
        publish=workflow.index("          name: three-venue-authenticated-native-sources")
        shutdown=workflow.index("      - name: Shut down upstream-backed fork")
        offline=workflow.index("  offline-amm-v4:")
        download=workflow.index("      - name: Import authenticated three-venue source evidence")
        signed=workflow.index("      - name: Verify registered Orca Whirlpool native pricing against signed Surfpool")
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
