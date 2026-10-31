import unittest
from arb.next_ten_fork_pool_probe import authenticated_distinct_venue_triangles as discover

def pool(venue,name,mints,slot=20):
    return {"venue":venue,"pool":name,"mints":mints,"slot":slot,
            "authenticated":True,"actionable":False,"live_execution_approved":False,
            "broadcast":False}
class Tests(unittest.TestCase):
    def inventory(self):
        return {
            "raydium_cpmm":[pool("raydium_cpmm","cpmm",["A","B"])],
            "orca":[pool("orca","whirlpool",["B","C"])],
            "raydium_amm_v4":[pool("raydium_amm_v4","v4",["C","A"])]}
    def test_three_real_distinct_venue_closed_mint_path(self):
        paths=discover(self.inventory())
        self.assertGreaterEqual(len(paths),1)
        self.assertTrue(any(r["route_venues"]==["raydium_cpmm","orca","raydium_amm_v4"]
                       and r["route_mints"]==["A","B","C","A"] for r in paths))
        self.assertTrue(all(len(set(r["route_venues"]))==3 for r in paths))
        self.assertTrue(all(not r["signed_atomic_simulation_verified"] and not r["broadcast"]
                            for r in paths))
    def test_same_two_mint_pair_is_not_a_triangle(self):
        pools=self.inventory()
        pools["orca"][0]["mints"]=["B","A"]
        self.assertEqual(discover(pools),[])
    def test_source_slot_and_authenticity_mandatory(self):
        for change in ({"authenticated":False},{"slot":None},{"pool":""}):
            pools=self.inventory()
            pools["orca"][0].update(change)
            with self.assertRaises(ValueError):discover(pools)
    def test_bound_route_inventory(self):
        self.assertEqual(len(discover(self.inventory(),limit=1)),1)
    def test_repeated_pool_rejected(self):
        pools=self.inventory();pools["orca"][0]["pool"]="cpmm"
        self.assertEqual(discover(pools),[])
if __name__=="__main__":unittest.main()
