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
    def test_budget_rejected(self):
        p=[self.pool("orca","a","SOL","USDC"),
           self.pool("raydium_cpmm","b","SOL","USDC")]
        with self.assertRaises(ValueError):
            cycles(p,anchors=["SOL"],max_cycles=1)
