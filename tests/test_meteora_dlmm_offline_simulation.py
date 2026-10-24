import os
import unittest
from unittest.mock import patch
from arb.meteora_dlmm_offline_simulation import attempt

class SignedDlmmOfflineSafetyTests(unittest.TestCase):
    @patch.dict(os.environ,{},clear=True)
    def test_no_explicit_offline_gate_rejects_before_any_rpc(self):
        with patch("arb.meteora_dlmm_offline_simulation.call") as rpc:
            with self.assertRaises(ValueError):
                attempt("http://127.0.0.1:8899",{})
            rpc.assert_not_called()

    @patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"1"})
    def test_remote_rpc_denied_before_any_rpc(self):
        with patch("arb.meteora_dlmm_offline_simulation.call") as rpc:
            with self.assertRaises(ValueError):
                attempt("https://api.mainnet-beta.solana.com",{})
            rpc.assert_not_called()

    @patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"1"})
    def test_fixture_provenance_denied_before_write(self):
        with patch("arb.meteora_dlmm_offline_simulation.call") as rpc:
            with self.assertRaisesRegex(ValueError,"authenticated read-only"):
                attempt("http://127.0.0.1:8899",{"source":"UNVERIFIED","venue":"meteora_dlmm"})
            rpc.assert_not_called()
