import unittest
from arb.orca_whirlpool import SOL,USDC
from arb.registry_multihop_cycles import discover_cycles

A="token-A";B="token-B";C="token-C";D="token-D"
def p(a,b,n,venue="orca",verified=True):
    return {"pool":n,"token_a":a,"token_b":b,"venue":venue,
            "all_pools_onchain_verified":verified}
class RegistryMultihopTests(unittest.TestCase):
    def test_two_hop_directed_cross_venue_and_reversal(self):
        cycles=discover_cycles([p(SOL,A,"one","orca"),p(SOL,A,"two","meteora_dlmm")],
                               starts=(SOL,))
        self.assertEqual(cycles["cycle_count"],2)
        self.assertTrue(all(x["tokens"]==[SOL,A,SOL] for x in cycles["cycles"]))
        self.assertTrue(all(len(set(l["pool"] for l in x["legs"]))==2 for x in cycles["cycles"]))
        self.assertFalse(any(x["actionable"] for x in cycles["cycles"]))
    def test_five_hop_with_no_intermediate_repeats(self):
        pools=[p(SOL,A,"1"),p(A,B,"2"),p(B,C,"3"),p(C,D,"4"),p(D,SOL,"5")]
        data=discover_cycles(pools,min_hops=5,max_hops=5,starts=(SOL,))
        self.assertEqual(data["cycle_count"],2)
        self.assertTrue(all(len(c["legs"])==5 for c in data["cycles"]))
        self.assertFalse(data["truncated"])
    def test_unverified_pools_excluded(self):
        d=discover_cycles([p(SOL,A,"1"),p(SOL,A,"2",verified=False)],starts=(SOL,))
        self.assertEqual(d["cycle_count"],0)
    def test_single_pool_cannot_backtrack_into_itself(self):
        self.assertEqual(discover_cycles([p(SOL,A,"1")],starts=(SOL,))["cycle_count"],0)
    def test_usdc_anchor_supported(self):
        data=discover_cycles([p(USDC,B,"a"),p(USDC,B,"b")],starts=(USDC,))
        self.assertEqual(data["cycle_count"],2)
        self.assertTrue(all(c["tokens"][0]==USDC for c in data["cycles"]))
    def test_bounded_and_deterministic(self):
        pools=[p(SOL,A,str(i)) for i in range(8)]
        a=discover_cycles(pools,starts=(SOL,),max_cycles=3)
        b=discover_cycles(list(reversed(pools)),starts=(SOL,),max_cycles=3)
        self.assertEqual(a["cycles"],b["cycles"])
        self.assertTrue(a["truncated"])
        with self.assertRaises(ValueError):
            discover_cycles(pools,max_hops=9)
