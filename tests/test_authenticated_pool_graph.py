import unittest
from arb.authenticated_pool_graph import enumerate_cycles,candidate_summary

def pool(venue,address,a,b,slot=100,**other):
    return {**{"venue":venue,"pool":address,"mints":[a,b],"slot":slot,
            "authenticated":True},**other}

class PoolGraphTests(unittest.TestCase):
    def test_cross_venue_two_hops_both_directions(self):
        data=[pool("orca","o","A","B"),pool("cpmm","c","A","B")]
        candidates=enumerate_cycles(data,start_mints=["A"])
        self.assertEqual(len(candidates),2)
        self.assertTrue(all(c["tokens"]==["A","B","A"] for c in candidates))
        self.assertEqual({tuple(e["venue"] for e in c["legs"]) for c in candidates},
                         {("orca","cpmm"),("cpmm","orca")})
    def test_six_hops_repeated_venues_distinct_pools(self):
        data=[pool("orca","o1","A","B"),pool("orca","o2","B","C"),
              pool("cpmm","c1","C","D"),pool("cpmm","c2","D","E"),
              pool("orca","o3","E","F"),pool("orca","o4","F","A")]
        routes=enumerate_cycles(data,start_mints=["A"],min_legs=6)
        self.assertEqual(len(routes),2)
        self.assertTrue(all(r["leg_count"]==6 for r in routes))
    def test_allows_different_pools_on_same_venue(self):
        routes=enumerate_cycles([pool("orca","a","X","Y"),
                                 pool("orca","b","X","Y")],start_mints=["X"])
        self.assertEqual(len(routes),2)
    def test_skips_invalid_stale_unauthenticated_and_inactive(self):
        data=[pool("orca","a","A","B",slot=99),
              pool("cpmm","b","A","B",slot=100),
              pool("other","c","A","B",slot=120,authenticated=False)]
        self.assertEqual(enumerate_cycles(data,start_mints=["A"],min_slot=100),[])
    def test_does_not_reuse_same_pool_in_two_leg_cycle(self):
        self.assertEqual(enumerate_cycles([pool("orca","a","A","B")],
                                           start_mints=["A"]),[])
    def test_duplicate_pool_identity_fail_closed(self):
        with self.assertRaises(ValueError):
            enumerate_cycles([pool("orca","a","A","B"),pool("orca","a","A","C")])
    def test_result_cap_and_safe_metadata(self):
        routes=enumerate_cycles([pool("orca","a","A","B"),
                                 pool("cpmm","b","A","B")],
                                start_mints=["A"],max_results=1)
        self.assertEqual(len(routes),1)
        self.assertFalse(routes[0]["broadcast"])
        self.assertFalse(candidate_summary([])["actionable"])
    def test_invalid_length_rejected(self):
        with self.assertRaises(ValueError):
            enumerate_cycles([],max_legs=7)

if __name__=="__main__":
    unittest.main()
