import unittest
from unittest.mock import patch
from arb.raydium_clmm_sixth_venue_source import capture,capture_pool

class RaydiumClmmSixthSourceSafetyTests(unittest.TestCase):
    def test_wrong_owner_rejected_before_followup_rpc(self):
        with patch("arb.raydium_clmm_sixth_venue_source.call",
                   return_value={"value":{"owner":"NotRaydium",
                           "executable":False,"data":["AQ==","base64"]}}) as rpc:
            with self.assertRaisesRegex(ValueError,"owner/executable"):
                capture_pool("https://readonly.example.org","A"*32,["B"*32,"C"*32])
            self.assertEqual(rpc.call_count,1)

    def test_cannot_claim_signed_admission_without_pool_account(self):
        registry={"pools":[{"venue":"raydium_clmm","address":"A"*32}]}
        with patch("arb.raydium_clmm_sixth_venue_source.call",
                   return_value={"value":None}):
            report=capture("https://readonly.example.org",registry,count=1)
        self.assertEqual(report["authenticated"],0)
        self.assertEqual(report["status"],"SIXTH_VENUE_SOURCE_RESEARCH")
        self.assertFalse(report["signed_parity_verified"])
        self.assertFalse(report["native_pricing_verified"])
        self.assertFalse(report["registry_admission_approved"])
        self.assertEqual(len(report["rejected"]),1)

    def test_bound_registry_only(self):
        with self.assertRaisesRegex(ValueError,"bounded"):
            capture("https://readonly.example.org",{"pools":[]},count=4)

if __name__=="__main__":unittest.main()
