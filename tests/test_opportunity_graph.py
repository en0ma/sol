import unittest
from arb.opportunity_graph import cycles
class OpportunityGraphTests(unittest.TestCase):
    def pool(self,v,a,x,y):
        return {"verified":True,"venue":v,"address":a,"mints":[x,y]}
    def test_finds_same_and_cross_venue_cycles(self):
        p=[self.pool("orca","pool-a","SOL","USDC"),
           self.pool("raydium_cpmm","pool-b","SOL","USDC"),
           self.pool("orca","pool-c","USDC","RAY"),
           self.pool("orca","pool-d","RAY","SOL")]
        paths=cycles(p,anchors=["SOL"])
        self.assertTrue(any(x["hops"]==2 for x in paths))
        self.assertTrue(any(x["hops"]==3 for x in paths))
        self.assertTrue(any(x["same_venue"] for x in paths))
        self.assertTrue(any(not x["same_venue"] for x in paths))
        self.assertTrue(all(x["net_profit_lamports"] is None for x in paths))
    def test_rejects_unverified_and_duplicate_pool_backtrack(self):
        p=[self.pool("orca","only","SOL","USDC")]
        self.assertEqual(cycles(p,anchors=["SOL"]),[])
        p[0]["verified"]=False
        self.assertEqual(cycles(p,anchors=["SOL"]),[])
    def test_raydium_amm_v4_joins_active_seven_venue_graph(self):
        p=[self.pool("raydium_amm_v4","v4","A","B"),
           self.pool("raydium_cpmm","cpmm","A","B")]
        routes=cycles(p,anchors=["A"])
        self.assertGreater(len(routes),0)
        self.assertTrue(any("raydium_amm_v4" in r["venues"] for r in routes))
    def test_budget_rejected(self):
        p=[self.pool("orca","a","SOL","USDC"),
           self.pool("raydium_cpmm","b","SOL","USDC")]
        with self.assertRaises(ValueError):
            cycles(p,anchors=["SOL"],max_cycles=1)
