"""Indexed Orca v1 pool addresses are only untrusted discovery hints."""
import unittest
from unittest.mock import patch
from arb.eight_venue_onchain_probe import probe

CANDIDATE="7qbRF6YsyGuLUVs6Y1q64bdVrfe4ZcUUz1JRdoVNUJnm"

class OrcaLegacyPublicCandidateTests(unittest.TestCase):
    def test_indexed_pool_requires_fork_authentication(self):
        with patch("arb.eight_venue_onchain_probe.verify_legacy",
                   side_effect=ValueError("Orca Token Swap pool owner mismatch")) as verify:
            report=probe("http://127.0.0.1:8899",{"pools":[]},
                         public_orca_legacy_candidates=[CANDIDATE])
        row=next(row for row in report["venues"]
                 if row["venue"]=="orca_token_swap_v1")
        verify.assert_called_once_with("http://127.0.0.1:8899",
                                      "orca_token_swap_v1",CANDIDATE)
        self.assertEqual(row["candidates_checked"],1)
        self.assertFalse(row["decoder_onchain_verified"])
        self.assertFalse(row["builder_onchain_execution_verified"])
        self.assertIn("owner mismatch",row["errors"][0])
        self.assertFalse(report["actionable"])
        self.assertFalse(report["live_execution_approved"])
        self.assertFalse(report["broadcast"])

    def test_duplicate_candidates_are_deduplicated(self):
        with patch("arb.eight_venue_onchain_probe.verify_legacy",
                   return_value={"pool_decoder_verified":True,
                                 "vaults_verified":True,"slot":123}) as verify:
            report=probe("http://127.0.0.1:8899",{"pools":[]},
                         public_orca_legacy_candidates=[CANDIDATE,CANDIDATE])
        row=next(row for row in report["venues"]
                 if row["venue"]=="orca_token_swap_v1")
        self.assertEqual(verify.call_count,1)
        self.assertEqual(row["candidates_checked"],1)
        self.assertTrue(row["decoder_onchain_verified"])
        self.assertFalse(row["builder_onchain_execution_verified"])

if __name__=="__main__":
    unittest.main()
