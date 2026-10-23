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
