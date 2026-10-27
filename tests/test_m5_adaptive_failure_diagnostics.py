import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from arb.m5_all_venue_adaptive_acceptance import audit

class AdaptiveFailureDiagnostics(unittest.TestCase):
    @patch("arb.m5_all_venue_adaptive_acceptance.route_batch")
    @patch("arb.m5_all_venue_adaptive_acceptance.check")
    def test_failure_identity_and_reasons_are_preserved(self,check,batch):
        batch.return_value=(("orca","raydium_cpmm"),("raydium_cpmm","orca"))
        check.return_value={"route":"orca__raydium_cpmm",
                            "status":"VERIFIED_ADAPTIVE_SIGNED_OFFLINE",
                            "failure_reasons":[]}
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/"orca__raydium_cpmm.json").write_text(json.dumps({"signed":True}))
            report=audit(d)
        self.assertEqual(report["target"],2)
        self.assertEqual(report["verified"],1)
        self.assertEqual(report["unverified_route_count"],1)
        self.assertEqual(report["unverified_routes"][0]["route"],"raydium_cpmm__orca")
        self.assertEqual(report["failure_reason_counts"]["signed adaptive receipt missing"],1)
        self.assertFalse(report["broadcast"])
        self.assertFalse(report["all_selected_signed_routes_verified"])
        self.assertEqual(report["complete_native_route_quotes_verified"],0)
        self.assertEqual(report["net_profitable_routes_verified"],0)
    @patch("arb.m5_all_venue_adaptive_acceptance.route_batch")
    @patch("arb.m5_all_venue_adaptive_acceptance.check")
    def test_dlmm_signed_failure_report_is_venue_specific_not_accepted(self,check,batch):
        batch.return_value=(("meteora_dlmm","orca"),("orca","raydium_cpmm"),
                            ("pumpswap","meteora_dlmm"))
        check.return_value={"route":"orca__raydium_cpmm",
             "status":"VERIFIED_ADAPTIVE_SIGNED_OFFLINE","failure_reasons":[]}
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/"orca__raydium_cpmm.json").write_text("{}")
            report=audit(d)
        self.assertEqual(report["verified"],1)
        self.assertEqual(report["unverified_route_count"],2)
        self.assertEqual(report["failing_venue_occurrences"]["meteora_dlmm"],2)
        self.assertEqual(report["venue_signed_coverage"]["meteora_dlmm"],
            {"attempted_route_occurrences":2,"verified_route_occurrences":0,
             "unverified_route_occurrences":2})
        self.assertEqual(report["venue_signed_coverage"]["orca"]["verified_route_occurrences"],1)
        self.assertEqual(report["dlmm_unverified_routes"],
            ["meteora_dlmm__orca","pumpswap__meteora_dlmm"])
        self.assertFalse(report["actionable"])

    @patch("arb.m5_all_venue_adaptive_acceptance.route_batch")
    @patch("arb.m5_all_venue_adaptive_acceptance.check")
    def test_verified_is_not_inferred_from_signed_receipt_presence(self,check,batch):
        batch.return_value=(("orca","raydium_cpmm"),)
        check.return_value={"route":"orca__raydium_cpmm",
              "status":"UNVERIFIED","failure_reasons":["signed intermediate SPL surplus nonzero"]}
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/"orca__raydium_cpmm.json").write_text("{}")
            report=audit(d)
        self.assertEqual(report["verified"],0)
        self.assertEqual(report["failure_reason_counts"]["signed intermediate SPL surplus nonzero"],1)
        self.assertEqual(report["unverified_route_count"],1)

if __name__=="__main__":
    unittest.main()
