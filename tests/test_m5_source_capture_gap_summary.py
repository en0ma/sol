"""Capture-gap diagnosis cannot conflate source failures with signed routes."""
import unittest
from arb.m5_three_hop_atomic_inventory import source_capture_gap_summary


class SourceCaptureGapTests(unittest.TestCase):
    def test_uncaptured_mints_partition_attempts_and_pool_diversity(self):
        report={"uncaptured_graph_start_mints":["A","B"],
                "blocked_source_routes":[
                    {"mints":["A","X","Y","A"],
                     "venues":["orca","meteora_dlmm","raydium_cpmm"],
                     "pools":["one","two","three"],
                     "source_status":"CAPTURE_BLOCKED",
                     "diagnostic":"ValueError: missing bin arrays"},
                    {"mints":["A","X","Z","A"],
                     "venues":["orca","meteora_dlmm","raydium_cpmm"],
                     "pools":["one","four","five"],
                     "source_status":"CAPTURE_BLOCKED",
                     "diagnostic":"private rpc URL not returned"},
                ]}
        result=source_capture_gap_summary(report)
        self.assertEqual(result["uncaptured_start_mints"],2)
        self.assertEqual(result["uncaptured_with_attempts"],1)
        self.assertEqual(result["uncaptured_without_attempts"],1)
        self.assertEqual(result["per_start_mint"]["A"]["distinct_attempted_pools"],5)
        self.assertEqual(result["per_start_mint"]["A"]["diagnostic_families"],
                         {"UNCLASSIFIED":1,"ValueError":1})
        self.assertTrue(result["per_start_mint"]["B"]["no_source_capture_attempt"])
        self.assertNotIn("private rpc",str(result))
        self.assertFalse(result["actionable"])
        self.assertTrue(result["not_signed_simulation_evidence"])

    def test_untrusted_status_and_duplicate_missing_mints_rejected(self):
        with self.assertRaises(ValueError):
            source_capture_gap_summary({"uncaptured_graph_start_mints":["A","A"],
                "blocked_source_routes":[]})
        with self.assertRaises(ValueError):
            source_capture_gap_summary({"uncaptured_graph_start_mints":["A"],
                "blocked_source_routes":[{"mints":["A"],"source_status":"CAPTURED"}]})

if __name__=="__main__":
    unittest.main()
