import copy
import unittest
from arb.execution_target_matrix import TARGET_VENUES
from arb.validate_eight_venue_probe import validate

def report():
    rows=[{"venue":name,"decoder_onchain_verified":False,
           "builder_code_present":True,"builder_onchain_execution_verified":False,
           "candidates_checked":0,"pool_evidence":None,"errors":[]} for name in TARGET_VENUES]
    return {"status":"SEVEN_VENUE_ONCHAIN_READONLY_PROBE",
            "decoder_verified_count":0,"builder_code_count":7,
            "builder_execution_verified_count":0,
            "venues":rows,"archived_optional_venues":["orca_token_swap_v1"],"actionable":False,"live_execution_approved":False,"broadcast":False}

class ValidateProbeTests(unittest.TestCase):
    def test_missing_pools_are_a_coverage_gap_not_fake_success(self):
        self.assertEqual(validate(report())["decoder_verified_count"],0)

    def test_six_standard_and_one_legacy_are_counted(self):
        data=report()
        for row in data["venues"][:6]:
            row["decoder_onchain_verified"]=True
            row["pool_evidence"]={"venue":row["venue"],"slot":42}
        data["venues"][6]["decoder_onchain_verified"]=True
        data["venues"][6]["pool_evidence"]={"pool_decoder_verified":True,"slot":42}
        data["decoder_verified_count"]=7
        self.assertEqual(validate(data)["decoder_verified_count"],7)

    def test_rejects_missing_safety_flag(self):
        data=report()
        data.pop("broadcast")
        with self.assertRaisesRegex(ValueError,"broadcast"):
            validate(data)

    def test_rejects_false_decoder_evidence(self):
        data=report()
        data["venues"][0]["decoder_onchain_verified"]=True
        data["decoder_verified_count"]=1
        with self.assertRaisesRegex(ValueError,"evidence"):
            validate(data)

    def test_rejects_signed_execution_claim(self):
        data=report()
        data["venues"][0]["builder_onchain_execution_verified"]=True
        with self.assertRaisesRegex(ValueError,"signed swap"):
            validate(data)

    def test_rejects_wrong_order_and_counts(self):
        data=report()
        data["venues"][0],data["venues"][1]=data["venues"][1],data["venues"][0]
        with self.assertRaisesRegex(ValueError,"identities"):
            validate(data)
        data=report()
        data["builder_code_count"]=7
        with self.assertRaisesRegex(ValueError,"counts"):
            validate(data)

if __name__=="__main__":
    unittest.main()
