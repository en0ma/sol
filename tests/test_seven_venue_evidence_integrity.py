import unittest
from arb.seven_venue_signed_parity_gate import summarize,ORDER

class Integrity(unittest.TestCase):
 def base(self):
  return {"venue":"orca","sample_status":"SIGNED_FORK_QUOTE_COMPARISON",
   "signed_simulation_accepted":True,"signed_input_base_units":100,
   "signed_output_base_units":90,"predicted_output_base_units":89,
   "source_slot":11,"source_manifest_sha256":"a"*64,
   "integer_delta_base_units":1,"absolute_integer_error_base_units":1,
   "exact_integer_match":False,"source_exact_protocol_verified":False,
   "actionable":False,"broadcast":False}
 def test_all_seven_explicit_and_real_delta(self):
  report=summarize([self.base()])
  self.assertEqual(set(report["by_venue"]),set(ORDER))
  self.assertEqual(report["by_venue"]["orca"]["largest_integer_error"],1)
  self.assertEqual(report["venue_coverage_count"],1)
 def test_forged_absolute_error_rejected(self):
  s=self.base();s["absolute_integer_error_base_units"]=0
  with self.assertRaises(ValueError):summarize([s])
 def test_blocked_venue_cannot_claim_exact_match(self):
  with self.assertRaises(ValueError):summarize([{
   "venue":"meteora_dlmm","sample_status":"SAMPLE_BLOCKED",
   "exact_integer_match":True}])
 def test_unsafe_rows_rejected(self):
  s=self.base();s["broadcast"]=True
  with self.assertRaises(ValueError):summarize([s])
if __name__=="__main__":unittest.main()
