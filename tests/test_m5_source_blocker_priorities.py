import unittest
from arb.m5_experiment_blocker_summary import summarize
class Tests(unittest.TestCase):
    def test_group_specific_real_quote_and_provenance_failures(self):
        rows=[{"route":"cpmm__v4","signed_proof_status":"VERIFIED",
               "full_intermediate_consumption_observed":True,
               "reason_codes":["SOURCE_TO_EXECUTION_PROVENANCE_UNVERIFIED",
                              "CPMM_EFFECTIVE_FEE_OR_RESERVES_UNAVAILABLE",
                              "ACCOUNT_DERIVED_QUOTE_BLOCKED: missing config"],
               "observed_input_quote_probes":[{"status":"UNVERIFIED"}],
               "captured_fee_and_compute":{"positive_units_consumed":430000,"fee_rows":[]}}]
        out=summarize(rows)
        self.assertEqual(out["issue_counts"]["SOURCE_PROVENANCE_UNVERIFIED"],1)
        self.assertEqual(out["issue_counts"]["CPMM_EFFECTIVE_PRICING_BLOCKED"],1)
        self.assertEqual(out["issue_counts"]["ACCOUNT_SOURCE_QUOTE_BLOCKED"],1)
        self.assertEqual(out["issue_counts"]["OBSERVED_INPUT_QUOTE_PROBE_BLOCKED"],1)
        self.assertEqual(out["independently_validated_quote_samples"],0)
        self.assertFalse(out["broadcast"])
    def test_duplicate_reasons_count_once_per_route(self):
        out=summarize([{"route":"A","reason_codes":["SOURCE_FIXTURE_MISSING","SOURCE_FIXTURE_MISSING"],
                        "captured_fee_and_compute":None}])
        self.assertEqual(out["issue_routes"]["SOURCE_FIXTURE_MISSING"],["A"])
        self.assertEqual(out["issue_counts"]["SOURCE_FIXTURE_MISSING"],1)
    def test_bad_probe_rejected(self):
        with self.assertRaisesRegex(ValueError,"invalid observed quote probe"):
            summarize([{"route":"A","reason_codes":[],"observed_input_quote_probes":[None]}])
if __name__=="__main__":unittest.main()
