"""Protect historical provenance versus usable-registry distinction."""
import unittest
from arb.six_venue_registry_eligibility import screen_signed_provenance

HEX = "a"*64
def row(venue="pumpswap", **changes):
    statuses={"pumpswap":"INDEPENDENT_SIGNED_NATIVE_SDK_SPL_PARITY",
              "meteora_dlmm":"INDEPENDENT_DLMM_SIGNED_NATIVE_SDK_SPL_PARITY",
              "raydium_clmm":"INDEPENDENT_CLMM_SIGNED_NATIVE_SDK_SPL_PARITY"}
    result={"venue":venue,"address":"pool1","mints":["A","B"],
            "signed_provenance":{"status":statuses.get(venue),
              "source_slot":100,"source_digest":HEX,
              "independent_receipt_sha256":HEX,
              "signed_transaction_hashes":[str(i)*64 for i in range(4)]}}
    result.update(changes)
    return result

class EligibilityTests(unittest.TestCase):
    def test_admitted_provenance_not_routable_without_fresh_state(self):
        result=screen_signed_provenance({"pools":[row()]})
        self.assertEqual(result["candidate_count"],1)
        self.assertEqual(result["coordinator_eligible_count"],0)
        self.assertFalse(result["candidates"][0]["current_quote_verified"])
        self.assertFalse(result["actionable"])
    def test_existing_legacy_evidence_not_erased_or_assumed_usable(self):
        result=screen_signed_provenance({"pools":[{"venue":"orca","address":"pool1"}]})
        self.assertEqual(result["blocked"][0]["reason"],"LEGACY_SIGNED_EVIDENCE_BRIDGE_REQUIRED")
    def test_malformed_or_unsigned_proof_fail_closed(self):
        for proof in (None, {}, {**row()["signed_provenance"],
                                  "signed_transaction_hashes":[HEX]*4}):
            with self.subTest(proof=proof):
                self.assertEqual(screen_signed_provenance({"pools":[
                    row(signed_provenance=proof)]})["candidate_count"],0)
    def test_duplicate_identity_rejected(self):
        with self.assertRaisesRegex(ValueError,"duplicate"):
            screen_signed_provenance({"pools":[row(),row()]})
    def test_unrelated_seventh_venue_excluded(self):
        out=screen_signed_provenance({"pools":[row("meteora_dbc")]})
        self.assertEqual(out["candidate_count"],0)
        self.assertFalse(out["broadcast"])

if __name__=="__main__":
    unittest.main()
