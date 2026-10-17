import unittest
from arb.opportunity_graph import cycles
from arb.cycle_inventory import inventory

class FullRouteCoverageTests(unittest.TestCase):
    def pool(self,venue,address,a="A",b="B"):
        return {"verified":True,"venue":venue,"address":address,"mints":[a,b]}

    def test_same_pool_roundtrip_is_not_blocked(self):
        found=cycles([self.pool("orca","pool")])
        self.assertEqual(len(found),2)
        self.assertTrue(all(x["hops"]==2 for x in found))
        self.assertTrue(all(len({y["pool"] for y in x["legs"]})==1 for x in found))

    def test_cross_pool_and_cross_venue_still_discovered(self):
        found=cycles([self.pool("orca","a"),
                      self.pool("raydium_cpmm","b")])
        self.assertTrue(any(len({e["pool"] for e in c["legs"]})>1 for c in found))
        self.assertTrue(any(not c["same_venue"] for c in found))

    def test_losing_cycles_remain_eligible_for_rescan(self):
        rows=[{"status":"INDICATIVE_ONLY","start_mint":"A",
               "input_base_units":100,
               "estimated_gross_base_units":-2,
               "route_legs":[{"venue":"orca","pool":"p"},
                             {"venue":"orca","pool":"p"}]}]
        entry=inventory(rows)[0]
        self.assertEqual(entry["topology"],"SAME_POOL")
        self.assertEqual(entry["current_priority"],"RESCAN_ON_NEXT_SNAPSHOT")
        self.assertTrue(entry["eligible_for_future_rescan"])
        self.assertFalse(entry["actionable"])
