import unittest
from arb.seven_venue_signed_parity_gate import summarize,ORDER

class Tests(unittest.TestCase):
 def test_every_venue_explicit_when_no_observations(self):
  r=summarize([])
  self.assertEqual(set(r["by_venue"]),set(ORDER))
  self.assertEqual(r["venue_coverage_count"],0)
  self.assertFalse(r["full_seven_venue_protocol_exact_verified"])
  self.assertTrue(all(row["compared"]==0 for row in r["by_venue"].values()))
 def test_integer_mismatch_detected_and_blockers_preserved(self):
  sample={"venue":"pumpswap","sample_status":"SIGNED_FORK_QUOTE_COMPARISON",
    "signed_simulation_accepted":True,"signed_input_base_units":100,
    "signed_output_base_units":99,"predicted_output_base_units":98,
    "source_slot":11,"source_manifest_sha256":"a"*64,
    "integer_delta_base_units":1,"exact_integer_match":False,
    "source_exact_protocol_verified":False}
  blocked={"venue":"meteora_dlmm","sample_status":"SAMPLE_BLOCKED",
           "reason":"live variable fee not decoded"}
  r=summarize([sample,blocked])
  self.assertEqual(r["by_venue"]["pumpswap"]["largest_integer_error"],1)
  self.assertEqual(r["by_venue"]["pumpswap"]["mismatched"],1)
  self.assertEqual(r["by_venue"]["meteora_dlmm"]["blocked"],1)
  self.assertEqual(r["venue_coverage_count"],1)
 def test_no_missing_or_fake_execution_counts(self):
  with self.assertRaises(ValueError):
   summarize([{"venue":"orca","sample_status":"SIGNED_FORK_QUOTE_COMPARISON",
               "signed_simulation_accepted":False}])
  with self.assertRaises(ValueError):
   summarize([{"venue":"unlisted","sample_status":"SAMPLE_BLOCKED"}])
 def test_strict_gate_remains_closed_without_all_venues(self):
  with self.assertRaises(ValueError):summarize([],strict=True)
if __name__=="__main__":unittest.main()
