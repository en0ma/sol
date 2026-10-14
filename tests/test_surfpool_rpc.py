"""Run with RUN_SURFPOOL_INTEGRATION=1 against a running offline Surfpool."""
import os
import unittest
from arb.rpc import call

@unittest.skipUnless(os.environ.get("RUN_SURFPOOL_INTEGRATION") == "1", "Surfpool integration disabled")
class SurfpoolIntegrationTests(unittest.TestCase):
    def test_rpc_blockhash(self):
        rpc = os.environ.get("SOLANA_RPC_URL", "http://127.0.0.1:8899")
        result = call(rpc, "getLatestBlockhash")
        self.assertTrue(result["value"]["blockhash"])

    def test_slot(self):
        rpc = os.environ.get("SOLANA_RPC_URL", "http://127.0.0.1:8899")
        self.assertIsInstance(call(rpc, "getSlot"), int)
