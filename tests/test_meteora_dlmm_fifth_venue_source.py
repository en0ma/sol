import unittest
from unittest.mock import patch

from arb.meteora_dlmm_fifth_venue_source import capture,capture_pool

REG={"pools":[{"venue":"meteora_dlmm","address":"A"*32,
               "mints":["X"*32,"Y"*32]}]}


class MeteoraDlmmFifthVenueSafetyTest(unittest.TestCase):
    def test_rejects_untrusted_source_owner_before_bin_fetch(self):
        with patch("arb.meteora_dlmm_fifth_venue_source.call",
                   return_value={"value":{"owner":"UnknownOwner",
                                         "executable":False,"data":["AA==","base64"]}}) as rpc:
            with self.assertRaisesRegex(ValueError,"source account owner"):
                capture_pool("https://readonly.example.com","A"*32,["X"*32,"Y"*32])
            self.assertEqual(rpc.call_count,1)

    def test_rejects_missing_pair_and_does_not_claim_signed_execution(self):
        with patch("arb.meteora_dlmm_fifth_venue_source.call",
                   return_value={"value":None}):
            report=capture("https://readonly.example.com",REG,count=1)
        self.assertEqual(report["authenticated"],0)
        self.assertEqual(report["status"],"FIFTH_VENUE_SOURCE_RESEARCH")
        self.assertFalse(report["signed_parity_verified"])
        self.assertFalse(report["native_pricing_verified"])
        self.assertFalse(report["registry_admission_approved"])
        self.assertFalse(report["broadcast"])
        self.assertEqual(len(report["rejected"]),1)

    def test_bounded_registry_hints_no_new_public_discovery(self):
        with self.assertRaisesRegex(ValueError,"bounded"):
            capture("https://readonly.example.com",REG,count=7)

    def test_duplicate_pool_identity_skipped(self):
        dup={"pools":[*REG["pools"],dict(REG["pools"][0])]}
        with patch("arb.meteora_dlmm_fifth_venue_source.call",
                   return_value={"value":None}) as rpc:
            report=capture("https://readonly.example.com",dup,count=1)
        self.assertEqual(rpc.call_count,1)
        self.assertEqual(len(report["rejected"]),1)


if __name__=="__main__":
    unittest.main()
