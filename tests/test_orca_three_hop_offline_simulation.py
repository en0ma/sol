import os
import unittest
from unittest.mock import patch
from arb.orca_three_hop_offline_simulation import offline_gate, hydrate_and_simulate
from arb.orca_whirlpool import SOL

class OfflineThreeHopGateTests(unittest.TestCase):
    @patch.dict(os.environ,{},clear=True)
    def test_no_explicit_offline_optin(self):
        with self.assertRaisesRegex(ValueError,"offline fixture writes prohibited"):
            offline_gate("http://127.0.0.1:8899")

    @patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"1"})
    def test_remote_rpc_always_rejected(self):
        with self.assertRaises(ValueError):
            offline_gate("https://api.mainnet-beta.solana.com")

    @patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"1"})
    def test_bare_loopback_allowed(self):
        self.assertIsNone(offline_gate("http://127.0.0.1:8899"))

    @patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"1"})
    def test_bad_provenance_rejected_before_any_write(self):
        with patch("arb.orca_three_hop_offline_simulation.call") as rpc:
            with self.assertRaisesRegex(ValueError,"untrusted fixture provenance"):
                hydrate_and_simulate("http://127.0.0.1:8899",{"source":"UNTRUSTED"})
            rpc.assert_not_called()

    @patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"1"})
    def test_nonclosed_route_rejected_before_any_write(self):
        with patch("arb.orca_three_hop_offline_simulation.call") as rpc:
            fixture={"source":"READ_ONLY_MAINNET_BACKED_SURFPOOL",
                     "route":{"tokens":[SOL,"a","b","other"],
                              "legs":[{}, {}, {}]}}
            with self.assertRaisesRegex(ValueError,"unsupported nonclosed route"):
                hydrate_and_simulate("http://127.0.0.1:8899",fixture)
            rpc.assert_not_called()
