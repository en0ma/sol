import unittest
from unittest.mock import patch
from arb.meteora_dlmm_fixture_export import export_dlmm_fixture

class DlmmExportSafetyTests(unittest.TestCase):
    def test_unverified_preflight_is_rejected_without_rpc_reads(self):
        with patch("arb.meteora_dlmm_fixture_export.call") as rpc:
            with self.assertRaisesRegex(ValueError,"authenticated active bin"):
                export_dlmm_fixture("http://127.0.0.1:8899",
                    {"status":"ACTIVE_BIN_ARRAY_ABSENT"},"/tmp/never-export-dlmm.json")
            rpc.assert_not_called()

    def test_absent_verified_oracle_is_rejected(self):
        with patch("arb.meteora_dlmm_fixture_export.check_active_bin_array") as verify:
            with self.assertRaisesRegex(ValueError,"authenticated DLMM oracle"):
                export_dlmm_fixture("http://127.0.0.1:8899",
                    {"status":"ACTIVE_BIN_ARRAY_AUTHENTICATED","pool":"any"},
                    "/tmp/never-export-dlmm.json")
            verify.assert_not_called()

    def test_remote_validator_fails_before_rpc(self):
        with patch("arb.meteora_dlmm_fixture_export.call") as rpc:
            with self.assertRaises(ValueError):
                export_dlmm_fixture("https://api.mainnet-beta.solana.com",{},
                    "/tmp/never-export-dlmm.json")
            rpc.assert_not_called()
