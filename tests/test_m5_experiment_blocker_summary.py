import unittest
from arb.m5_experiment_blocker_summary import summarize
class Tests(unittest.TestCase):
    def test_classifies_observed_research_gaps(self):
        r=summarize([{"route":"cpmm__v4","signed_proof_status":"VERIFIED",
         "full_intermediate_consumption_observed":False,
         "reason_codes":["CPMM_EFFECTIVE_FEE_OR_RESERVES_UNAVAILABLE"],
         "captured_fee_and_compute":{"fee_rows":[{"blocker":"CPMM_CREATOR_FEE_PLACEMENT_UNVERIFIED"}],
         "positive_units_consumed":123}}])
        self.assertEqual(r["issue_counts"]["FULL_INTERMEDIATE_NOT_VERIFIED"],1)
        self.assertEqual(r["issue_counts"]["CPMM_CREATOR_FEE_PLACEMENT_UNVERIFIED"],1)
        self.assertNotIn("SIGNED_COMPUTE_MISSING",r["issue_counts"])
        self.assertEqual(r["independently_validated_quote_samples"],0)
        self.assertFalse(r["broadcast"])
    def test_missing_measured_cost_is_explicit(self):
        r=summarize([{"route":"a","reason_codes":[],"captured_fee_and_compute":{}}])
        self.assertIn("SIGNED_COMPUTE_MISSING",r["issue_counts"])
    def test_bad_row_is_refused(self):
        with self.assertRaises(ValueError):summarize([{}])
if __name__=="__main__": unittest.main()
