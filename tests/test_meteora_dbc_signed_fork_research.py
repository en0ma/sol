"""DBC signed research must never reach a mainnet broadcast path."""
import unittest
from unittest.mock import patch
from arb.meteora_dbc_signed_fork_research import diagnostic,restore


class DbCOfflineSignedResearchSafety(unittest.TestCase):
    def test_public_rpc_cannot_be_simulation_destination(self):
        with self.assertRaises((ValueError,OSError,RuntimeError)):
            diagnostic("https://readonly.invalid","https://api.mainnet-beta.solana.com",
                       {},{},{},required=1)

    def test_missing_curve_acceptance_rejected_before_program_hydration(self):
        with patch("arb.meteora_dbc_signed_fork_research.program_data_accounts") as program:
            with self.assertRaisesRegex(ValueError,"unsigned source"):
                diagnostic("https://readonly.invalid","http://127.0.0.1:8899",
                           {},{},{},required=1)
            program.assert_not_called()

    def test_original_account_digest_tampering_rejected_before_rpc(self):
        with patch("arb.meteora_dbc_signed_fork_research.call") as rpc:
            with self.assertRaisesRegex(ValueError,"hash changed"):
                restore("http://127.0.0.1:8899","11111111111111111111111111111111",
                   {"executable":False,"account_base64":"AQ==",
                    "sha256":"0"*64,"owner":"11111111111111111111111111111111",
                    "lamports":1})
            rpc.assert_not_called()


if __name__=="__main__":unittest.main()
