import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from arb.m5_all_venue_adaptive_acceptance import audit
class Tests(unittest.TestCase):
    def test_focused_selection_targets_twelve_not_full_remaining_batch(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            result=audit(Path(d),batch="remaining",only_venue="raydium_amm_v4")
        self.assertEqual(result["target"],12)
        self.assertEqual(result["verified"],0)
        self.assertEqual(len(result["routes"]),12)
        self.assertTrue(all("raydium_amm_v4" in row["route"] for row in result["routes"]))
    def test_missing_all_route_receipts_not_promoted(self):
        with tempfile.TemporaryDirectory() as d:
            result=audit(Path(d),batch="remaining")
        self.assertGreater(result["target"],2)
        self.assertEqual(result["verified"],0)
        self.assertFalse(result["full_42_adaptive_verified"])
        self.assertFalse(result["broadcast"])
    def test_real_signed_receipts_must_pass_independent_gate(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"orca__raydium_amm_v4.json"
            p.write_text("{}")
            with patch("arb.m5_all_venue_adaptive_acceptance.check",return_value={
                "route":"orca__raydium_amm_v4","status":"UNVERIFIED","failure_reasons":["missing CPI proof"]}):
                result=audit(Path(d),batch="remaining")
        self.assertEqual(result["verified"],0)
if __name__=="__main__":unittest.main()
