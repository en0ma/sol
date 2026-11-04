import unittest
from unittest.mock import patch
from arb.onchain_history_discovery import discover_history
class HistoryDiscoveryTests(unittest.TestCase):
    @patch("arb.onchain_history_discovery.call")
    def test_empty_history_is_not_fake_pool(self,call):
        call.return_value=[]
        out=discover_history("rpc",("orca",),1)
        self.assertEqual(out["pools"],[])
        self.assertEqual(out["status"],"COMPLETE")
    @patch("arb.onchain_history_discovery.call")
    def test_history_failures_explicit(self,call):
        call.side_effect=RuntimeError("throttled")
        out=discover_history("rpc",("orca",),1)
        self.assertEqual(out["status"],"PARTIAL")
        self.assertEqual(out["errors"][0]["stage"],"signatures")
    def test_bounded_history(self):
        with self.assertRaises(ValueError):
            discover_history("rpc",("orca",),21)
