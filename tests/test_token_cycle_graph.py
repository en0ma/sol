import unittest
from arb.token_cycle_graph import candidate_cycles

S="So11111111111111111111111111111111111111112"
U="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
R="4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"

def pool(name,venue,a,b):
    return {"address":name,"venue":venue,"mints":[a,b]}

class CycleGraphTests(unittest.TestCase):
    def test_triangular_cross_venue_and_same_venue_cycles(self):
        entries=[pool("a","orca",S,U),pool("b","raydium",U,R),
                 pool("c","orca",R,S),pool("d","orca",S,U),
                 pool("e","orca",U,R)]
        report=candidate_cycles(entries,starts=(S,))
        three=[c for c in report["cycles"] if c["hops"]==3]
        two=[c for c in report["cycles"] if c["hops"]==2]
        self.assertTrue(any(len(c["venues"])==2 for c in three))
        self.assertTrue(any(len(c["venues"])==1 for c in three))
        self.assertTrue(two)
        for cycle in report["cycles"]:
            self.assertEqual(cycle["tokens"][0],cycle["tokens"][-1])
            self.assertEqual(len({leg["pool"] for leg in cycle["legs"]}),cycle["hops"])
            self.assertFalse(cycle["actionable"])
            self.assertFalse(cycle["simulation_verified"])
            self.assertFalse(cycle["broadcast"])

    def test_unconnected_and_missing_mint_hints_do_not_invent_cycles(self):
        report=candidate_cycles([pool("a","orca",S,U),
                                  pool("b","raydium",U,R),
                                  {"address":"unknown","venue":"orca"}],starts=(S,))
        self.assertEqual(report["cycles_returned"],0)
        self.assertEqual(len(report["rejected_hints"]),1)

    def test_both_anchors_receive_budget_under_truncation(self):
        entries=[]
        for i in range(8):
            entries.append(pool("sol-left-"+str(i),"orca",S,R))
            entries.append(pool("sol-right-"+str(i),"orca",R,S))
            entries.append(pool("usdc-left-"+str(i),"orca",U,R))
            entries.append(pool("usdc-right-"+str(i),"orca",R,U))
        report=candidate_cycles(entries,starts=(S,U),max_cycles=20)
        self.assertEqual(report["cycles_by_start"][S],10)
        self.assertEqual(report["cycles_by_start"][U],10)
        self.assertEqual(report["cycles_returned"],20)
        self.assertTrue(all(c["tokens"][0]==c["tokens"][-1]
                            for c in report["cycles"]))

    def test_bounded_and_no_reuse_of_same_pool(self):
        with self.assertRaises(ValueError):
            candidate_cycles([],max_cycles=201)
        report=candidate_cycles([pool("a","orca",S,U)],starts=(S,))
        self.assertEqual(report["cycles_returned"],0)
