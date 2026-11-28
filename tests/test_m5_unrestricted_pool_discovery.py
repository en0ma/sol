import unittest
from unittest.mock import patch
from arb.paginated_top_pool_discovery import campaign,FEEDS
from arb.onchain_pool_discovery import VENUES

class UnrestrictedDiscoveryTests(unittest.TestCase):
    def test_all_discovered_bypasses_400_registry_boundary_and_balances_feeds(self):
        existing=[{"venue":"orca","address":"old"+str(i),"mints":["A","B"]}
                  for i in range(800)]
        visited=[]
        def page(n,feed):
            visited.append((n,feed))
            return [{"address":"new"+feed+str(i)} for i in range(3)]
        def verify(rpc,rows):
            return {"verified_pools":[{**rows[0],"mints":["C","D"],"slot":123}],"rejected":[]}
        with patch("arb.paginated_top_pool_discovery.top_page",side_effect=page),patch(
                "arb.paginated_top_pool_discovery.call",
                return_value={"value":{"owner":VENUES["orca"][0]}}),patch(
                "arb.paginated_top_pool_discovery.refresh",side_effect=verify):
            result=campaign("http://127.0.0.1:8899",existing,all_discovered=True,
                max_pages=len(FEEDS),secondary_mint_limit=0,pace=0)
        self.assertEqual(visited,[(1,feed[0]) for feed in FEEDS])
        self.assertEqual(result["authenticated_new_pool_count"],3*len(FEEDS))
        self.assertEqual(result["candidate_registry_pool_count"],800+3*len(FEEDS))
        self.assertIsNone(result["pool_count_limit"])
        self.assertFalse(result["global_pool_enumeration_exhaustive"])
        self.assertFalse(result["broadcast"])

    def test_elapsed_deadline_stops_without_claiming_exhaustive_discovery(self):
        with patch("arb.paginated_top_pool_discovery.time.monotonic",return_value=10),patch(
                "arb.paginated_top_pool_discovery.top_page") as fetch:
            result=campaign("http://127.0.0.1:8899",[],all_discovered=True,
                max_pages=50,secondary_mint_limit=None,deadline=9,pace=0)
        fetch.assert_not_called()
        self.assertEqual(result["stop_reason"],"TIME_BUDGET_REACHED")
        self.assertEqual(result["status"],"PARTIAL")
        self.assertFalse(result["global_pool_enumeration_exhaustive"])

if __name__=="__main__":unittest.main()
