"""DBC independent signed acceptance is impossible without real source receipts."""
import unittest
from arb.meteora_dbc_signed_audit import audit


class DbcIndependentSignedBoundaryTests(unittest.TestCase):
    def test_empty_untrusted_receipts_do_not_verify(self):
        source={"status":"DBC_ORIGINAL_CONTEXTUAL_SOURCE_PARTIAL_NOT_SIGNED"}
        sdk={"status":"DBC_ORIGINAL_OFFICIAL_SDK_QUOTES_ONLY_NOT_NATIVE_PARITY"}
        native={"status":"INDEPENDENT_DBC_ORIGINAL_NATIVE_FEE_CURVE_SDK_PARITY",
                "verified_pools":1,"verified_trials":4}
        signed={"status":"DBC_SIGNED_OFFLINE_DIAGNOSTIC_NOT_ACCEPTED",
                "independent_signed_audit_accepted":False,"actionable":False,
                "broadcast":False,"pools":[]}
        with self.assertRaisesRegex(ValueError,"four-signature-per-pool"):
            audit(source,sdk,native,signed,required=1)

    def test_no_signed_status_substitution(self):
        with self.assertRaisesRegex(ValueError,"prerequisite absent"):
            audit({}, {}, {}, {"status":"CI_SUCCESS"},required=1)

    def test_non_six_required_count_rejected(self):
        with self.assertRaisesRegex(ValueError,"prerequisite absent"):
            audit({}, {}, {}, {},required=7)


if __name__=="__main__":unittest.main()
