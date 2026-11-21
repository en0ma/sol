import unittest
from unittest.mock import patch
from solders.keypair import Keypair
from arb.orca_swap_v2_isolated_offline_execution import hydrate_and_attempt

class IsolatedOrcaExecutionTests(unittest.TestCase):
    def test_refuses_provisioning_without_explicit_offline_opt_in(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "explicit offline"):
                hydrate_and_attempt("http://127.0.0.1:8899", "/not/read")
    def test_refuses_remote_rpc_even_with_offline_flag(self):
        with patch.dict("os.environ", {"SURFPOOL_EXPLICITLY_OFFLINE": "1"}):
            with self.assertRaises(ValueError):
                hydrate_and_attempt("https://api.mainnet-beta.solana.com", "/not/read")
