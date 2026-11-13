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
    def test_bounded_discovery_keeps_partial_cycle_evidence(self):
        pools=[self.pool("orca","p-o","A","B"),
               self.pool("raydium_cpmm","p-c","A","B")]
        routes=cycles(pools,anchors=["A"],max_cycles=1,truncate=True)
        self.assertEqual(len(routes),1)
        self.assertEqual(routes[0]["hops"],2)
        with self.assertRaises(ValueError):
            cycles(pools,anchors=["A"],max_cycles=1)
    def test_six_hop_cycles_are_reachable_through_same_graph(self):
        mints=["A","B","C","D","E","F"]
        venues=["orca","raydium_cpmm","raydium_clmm","raydium_amm_v4",
                "meteora_dlmm","pumpswap"]
        pools=[self.pool(venues[i],"p"+str(i),mints[i],mints[(i+1)%6])
               for i in range(6)]
        result=cycles(pools,anchors=["A"],max_hops=6,min_hops=6)
        self.assertTrue(any(row["hops"]==6 for row in result))
        self.assertEqual(cycles(pools,anchors=["A"],max_hops=5,min_hops=5),[])
        with self.assertRaises(ValueError):
            cycles(pools,min_hops=7,max_hops=6)
    def test_budget_rejected(self):
        p=[self.pool("orca","a","SOL","USDC"),
           self.pool("raydium_cpmm","b","SOL","USDC")]
        with self.assertRaises(ValueError):
            cycles(p,anchors=["SOL"],max_cycles=1)
