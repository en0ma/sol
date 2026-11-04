import unittest
from arb.opportunity_graph import cycles
from arb.cycle_inventory import inventory

class FullRouteCoverageTests(unittest.TestCase):
    def pool(self,venue,address,a="A",b="B"):
        return {"verified":True,"venue":venue,"address":address,"mints":[a,b]}

    def test_same_pool_roundtrip_is_excluded(self):
        self.assertEqual(cycles([self.pool("orca","pool")]),[])

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
                             {"venue":"orca","pool":"q"}]}]
        entry=inventory(rows)[0]
        self.assertEqual(entry["topology"],"SAME_VENUE_MULTIPOOL")
        self.assertEqual(entry["current_priority"],"RESCAN_ON_NEXT_SNAPSHOT")
        self.assertTrue(entry["eligible_for_future_rescan"])
        self.assertFalse(entry["actionable"])

    def test_inventory_rejects_reused_pool(self):
        rows=[{"status":"INDICATIVE_ONLY","route_legs":[
            {"venue":"orca","pool":"p"},{"venue":"orca","pool":"p"}]}]
        self.assertEqual(inventory(rows),[])
