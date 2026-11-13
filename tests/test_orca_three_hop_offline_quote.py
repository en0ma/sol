import os
import unittest
from unittest.mock import patch
from arb.orca_three_hop_offline_simulation import quote_hops_offline

class OfflineQuoteGateTests(unittest.TestCase):
    @patch.dict(os.environ,{},clear=True)
    def test_quotes_cannot_mutate_nonexplicit_offline_validator(self):
        with patch("arb.orca_three_hop_offline_simulation.call") as rpc:
            with self.assertRaisesRegex(ValueError,"offline fixture writes prohibited"):
                quote_hops_offline("http://127.0.0.1:8899",{}, {}, {}, {}, None)
            rpc.assert_not_called()

    @patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"1"})
    def test_remote_rpc_rejected_before_quote_reads_and_writes(self):
        with patch("arb.orca_three_hop_offline_simulation.call") as rpc:
            with self.assertRaises(ValueError):
                quote_hops_offline("https://api.mainnet-beta.solana.com",{}, {}, {}, {}, None)
            rpc.assert_not_called()
