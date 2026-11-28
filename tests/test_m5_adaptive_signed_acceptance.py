import unittest
from unittest.mock import patch
from arb.m5_adaptive_signed_acceptance import check,audit,PAIRS
class Tests(unittest.TestCase):
    def receipt(self):
        return {"adaptive_second_input_verified_against_atomic_output":True,
           "signed_second_leg_consumes_full_first_output":True,
           "adaptive_cpmm_v4_amount_planning":{"standalone_signed":True,"planned_second_input":80},
           "declared_second_leg_input_base_units":80,
           "first_leg_intermediate_received_base_units":80,
           "second_leg_intermediate_consumed_base_units":80,
           "signed_intermediate_surplus_base_units":0}
    def test_complete_signed_adaptive_amount_evidence(self):
        with patch("arb.m5_adaptive_signed_acceptance.assess",return_value={"failure_reasons":[]}):
            r=check(PAIRS[0],self.receipt())
        self.assertEqual(r["status"],"VERIFIED_ADAPTIVE_SIGNED_OFFLINE")
        self.assertFalse(r["quote_accuracy_verified"])
    def test_partial_consumption_fails(self):
        r=self.receipt();r["second_leg_intermediate_consumed_base_units"]=100
        with patch("arb.m5_adaptive_signed_acceptance.assess",return_value={"failure_reasons":[]}):
            x=check(PAIRS[1],r)
        self.assertEqual(x["status"],"UNVERIFIED")
    def test_atomic_failure_cannot_be_promoted(self):
        with patch("arb.m5_adaptive_signed_acceptance.assess",return_value={"failure_reasons":["rollback unverified"]}):
            r=check(PAIRS[0],self.receipt())
        self.assertEqual(r["status"],"UNVERIFIED")
    def test_missing_artifacts_fail_closed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            a=audit(d)
        self.assertEqual(a["verified"],0)
        self.assertFalse(a["broadcast"])
if __name__=="__main__":unittest.main()
