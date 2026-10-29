import unittest
from copy import deepcopy

from arb.pumpswap_sdk_candidate_audit import audit


def fixture():
    mint_a="A"*32
    mint_b="B"*32
    address="P"*32
    rows=[{"input_mint":mint,"amount_in":size,
           "official_sdk_output":"100","python_candidate_output":"100",
           "status":"OFFICIAL_SDK_CANDIDATE_EXACT","signed_parity_verified":False}
          for mint in (mint_a,mint_b) for size in (10000,100000)]
    source={"venue":"pumpswap","pools":[{"address":address,
            "status":"AUTHENTICATED_SOURCE_ONLY","mints":[mint_a,mint_b],
            "verified_snapshot_slot":42,"authenticated_source_sha256":"a"*64,
            "native_quote_candidates":[{"mint_in":r["input_mint"],"amount_in":r["amount_in"],
                "native_formula_candidate_out":100,"status":"UNVERIFIED_NATIVE_FORMULA_CANDIDATE"}
                for r in rows]}]}
    sdk={"venue":"pumpswap","signed_parity_verified":False,"actionable":False,
         "registry_admission_approved":False,"sdk_candidate_verified_pools":1,
         "pools":[{"address":address,"source_slot":42,"signed_parity_verified":False,
                   "actionable":False,"trials":rows}]}
    return source,sdk


class PumpSwapSdkCandidateAuditTest(unittest.TestCase):
    def test_four_independent_sdk_matches_are_still_not_signed_proof(self):
        source,sdk=fixture()
        result=audit(source,sdk)
        self.assertEqual(result["sdk_candidate_matched_pools"],1)
        self.assertFalse(result["signed_parity_verified"])
        self.assertFalse(result["registry_admission_approved"])

    def test_rejects_source_slot_mismatch(self):
        source,sdk=fixture()
        sdk["pools"][0]["source_slot"]=43
        with self.assertRaisesRegex(ValueError,"snapshot slot disagreement"):
            audit(source,sdk)

    def test_rejects_missing_authenticated_source_digest(self):
        source,sdk=fixture()
        source["pools"][0].pop("authenticated_source_sha256")
        with self.assertRaisesRegex(ValueError,"digest missing"):
            audit(source,sdk)

    def test_rejects_mismatched_integer_price(self):
        source,sdk=fixture()
        sdk["pools"][0]["trials"][0]["python_candidate_output"]="101"
        with self.assertRaisesRegex(ValueError,"pricing disagreement"):
            audit(source,sdk)

    def test_rejects_duplicate_direction_or_amount(self):
        source,sdk=fixture()
        sdk["pools"][0]["trials"][0]["amount_in"]=100000
        with self.assertRaisesRegex(ValueError,"duplicate"):
            audit(source,sdk)

    def test_rejects_forged_sdk_receipt_matching_only_its_own_output(self):
        source,sdk=fixture()
        sdk["pools"][0]["trials"][0]["official_sdk_output"]="101"
        sdk["pools"][0]["trials"][0]["python_candidate_output"]="101"
        with self.assertRaisesRegex(ValueError,"authenticated source candidate"):
            audit(source,sdk)

    def test_rejects_duplicate_source_trial(self):
        source,sdk=fixture()
        source["pools"][0]["native_quote_candidates"][0]["amount_in"]=100000
        with self.assertRaisesRegex(ValueError,"duplicate"):
            audit(source,sdk)

    def test_rejects_missing_signed_denial(self):
        source,sdk=fixture()
        sdk["signed_parity_verified"]=True
        with self.assertRaisesRegex(ValueError,"cannot certify signed"):
            audit(source,sdk)

    def test_rejects_incomplete_comparisons(self):
        source,sdk=fixture()
        sdk["pools"][0]["trials"].pop()
        with self.assertRaisesRegex(ValueError,"four SDK"):
            audit(source,sdk)

    def test_rejects_unauthenticated_source(self):
        source,sdk=fixture()
        source["pools"][0]["status"]="SOURCE_REJECTED"
        with self.assertRaisesRegex(ValueError,"unauthenticated"):
            audit(source,sdk)


if __name__=="__main__":
    unittest.main()
