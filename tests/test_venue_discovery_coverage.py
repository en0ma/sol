import unittest
from unittest.mock import patch
from arb.onchain_pool_discovery import discover,VENUES

class VenueDiscoveryCoverageTests(unittest.TestCase):
    @patch("arb.onchain_pool_discovery.search_pair")
    def test_rate_limit_records_untested_venues(self,search):
        search.side_effect=RuntimeError("429 Too Many Requests")
        result=discover("http://127.0.0.1:8899",[("mintA","mintB")])
        self.assertEqual(result["status"],"UPSTREAM_RATE_LIMITED")
        self.assertEqual(sum(v["attempted_pairs"] for v in result["venue_attempts"].values()),1)
        self.assertEqual(sum(v["status"]=="SKIPPED_UPSTREAM_RATE_LIMIT"
                             for v in result["venue_attempts"].values()),len(VENUES)-1)
        self.assertEqual(result["pools_verified"],0)

    @patch("arb.onchain_pool_discovery.search_pair",return_value={})
    def test_every_venue_is_attempted_with_healthy_rpc(self,search):
        result=discover("http://127.0.0.1:8899",[("mintA","mintB")])
        self.assertEqual(result["status"],"COMPLETE")
        self.assertEqual(set(result["venue_attempts"]),set(VENUES))
        self.assertTrue(all(v["attempted_pairs"]==1 and v["status"]=="SEARCHED"
                            for v in result["venue_attempts"].values()))
