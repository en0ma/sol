import unittest
from unittest.mock import patch
from arb.onchain_pool_discovery import discover, VENUES

class TargetedVenueDiscoveryTests(unittest.TestCase):
    @patch("arb.onchain_pool_discovery.search_pair")
    def test_rate_limit_does_not_mislabel_unselected_venues(self,search):
        search.side_effect=RuntimeError("429 Too Many Requests")
        result=discover("http://127.0.0.1:8899",[("A","B")],
                        venues=["meteora_dlmm"])
        self.assertEqual(result["venue_attempts"]["meteora_dlmm"]["status"],
                         "RATE_LIMITED")
        for venue in VENUES:
            if venue!="meteora_dlmm":
                self.assertEqual(result["venue_attempts"][venue]["status"],
                                 "NOT_SELECTED")

    @patch("arb.onchain_pool_discovery.search_pair",return_value={})
    def test_targeted_pumpswap_still_attempted(self,search):
        result=discover("http://127.0.0.1:8899",[("A","B")],
                        venues=["pumpswap"])
        self.assertEqual(result["venue_attempts"]["pumpswap"]["status"],"SEARCHED")
        self.assertEqual(search.call_args.args[1],"pumpswap")

    def test_duplicate_venue_selection_rejected(self):
        with self.assertRaises(ValueError):
            discover("rpc",[],venues=["pumpswap","pumpswap"])
