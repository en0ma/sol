import unittest
from unittest.mock import patch
from arb.atomic_cycle_builder import sign_atomic

class AtomicCycleBuilderTests(unittest.TestCase):
    @patch("arb.atomic_cycle_builder.local_rpc_only")
    def test_rejects_invalid_leg_counts(self,local):
        for legs in ([],[object()],[object()]*5):
            with self.assertRaises(ValueError):
                sign_atomic("http://127.0.0.1:8899",None,legs)
    @patch("arb.atomic_cycle_builder.local_rpc_only")
    def test_rejects_unverified_instruction_types(self,local):
        try:
            from solders.keypair import Keypair
        except ImportError:
            self.skipTest("solders only installed in Surfpool fork job")
        with self.assertRaisesRegex(ValueError,"verified builders"):
            sign_atomic("http://127.0.0.1:8899",Keypair(),[object(),object()])
    @patch("arb.atomic_cycle_builder.local_rpc_only")
    def test_fails_before_network_when_remote(self,local):
        local.side_effect=ValueError("remote RPC")
        with self.assertRaisesRegex(ValueError,"remote RPC"):
            sign_atomic("https://mainnet.example",None,[object(),object()])
