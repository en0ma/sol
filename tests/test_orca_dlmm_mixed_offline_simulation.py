import os
import unittest
from unittest.mock import patch
from arb.orca_dlmm_mixed_offline_simulation import attempt

class MixedAtomicOfflineSafetyTests(unittest.TestCase):
    @patch.dict(os.environ,{},clear=True)
    def test_no_offline_opt_in_blocks_before_rpc(self):
        with patch("arb.orca_dlmm_mixed_offline_simulation.call") as rpc:
            with self.assertRaises(ValueError):
                attempt("http://127.0.0.1:8899",{})
            rpc.assert_not_called()

    @patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"1"})
    def test_remote_rpc_blocked_before_reads_and_writes(self):
        with patch("arb.orca_dlmm_mixed_offline_simulation.call") as rpc:
            with self.assertRaises(ValueError):
                attempt("https://api.mainnet-beta.solana.com",{})
            rpc.assert_not_called()

    @patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"1"})
    def test_unverified_fixture_blocked(self):
        with patch("arb.orca_dlmm_mixed_offline_simulation.call") as rpc:
            with self.assertRaisesRegex(ValueError,"untrusted mixed fixture"):
                attempt("http://127.0.0.1:8899",{"source":"UNTRUSTED"})
            rpc.assert_not_called()
