import unittest
from unittest.mock import patch
from arb.eight_venue_onchain_probe import probe,BUILDERS,LEGACY
from arb.execution_target_matrix import TARGET_VENUES

class EightVenueOnchainProbeTests(unittest.TestCase):
    def test_all_eight_have_builder_module_mapping(self):
        self.assertEqual(set(BUILDERS),set(TARGET_VENUES))
        self.assertEqual(set(LEGACY),{"raydium_amm_v4","orca_token_swap_v1"})

    def test_reject_external_rpc_before_fetch(self):
        with patch("arb.eight_venue_onchain_probe.call") as rpc:
            with self.assertRaises(ValueError):
                probe("https://api.mainnet-beta.solana.com",{"pools":[]})
            rpc.assert_not_called()

    def test_empty_registry_never_claims_onchain_verification(self):
        report=probe("http://127.0.0.1:8899",{"pools":[]})
        self.assertEqual(len(report["venues"]),8)
        self.assertEqual(report["decoder_verified_count"],0)
        self.assertEqual(report["builder_execution_verified_count"],0)
        self.assertFalse(report["broadcast"])

    def test_discovery_fills_missing_legacy_candidates_without_execution_approval(self):
        with patch("arb.legacy_pool_discovery.discover",return_value=["legacy-pool"]) as discover:
            with patch("arb.eight_venue_onchain_probe.verify_legacy",return_value={
                "pool_decoder_verified":True,"vaults_verified":True,"slot":1}) as verify:
                report=probe("http://127.0.0.1:8899",{"pools":[]},
                             discover_legacy=True)
        self.assertEqual(discover.call_count,2)
        self.assertEqual(verify.call_count,2)
        self.assertEqual(report["decoder_verified_count"],2)
        self.assertEqual(report["builder_execution_verified_count"],0)
        self.assertFalse(report["live_execution_approved"])

    def test_rate_limited_legacy_discovery_preserves_evidence_report(self):
        from arb.rpc import RPCError
        with patch("arb.legacy_pool_discovery.discover",
                   side_effect=RPCError("429 Too Many Requests")):
            report=probe("http://127.0.0.1:8899",{"pools":[]},
                         discover_legacy=True)
        self.assertEqual(len(report["venues"]),8)
        self.assertEqual(report["decoder_verified_count"],0)
        self.assertEqual(report["builder_execution_verified_count"],0)
        for row in report["venues"]:
            if row["venue"] in LEGACY:
                self.assertIn("429",row["errors"][0])
