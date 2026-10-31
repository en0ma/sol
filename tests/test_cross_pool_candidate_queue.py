import unittest
from arb.cross_pool_candidate_queue import shortlist

class CrossPoolQueueTests(unittest.TestCase):
    def route(self,pools,gross):
        return {"status":"INDICATIVE_ONLY","start_mint":"mint",
                "input_base_units":100000,
                "estimated_gross_base_units":gross,
                "route_legs":[{"pool":p,"venue":("orca" if i%2 else "raydium_clmm")}
                              for i,p in enumerate(pools)]}
    def test_same_pool_roundtrip_excluded(self):
        results=shortlist([self.route(["A","A"],9999),
                           self.route(["A","B"],10),
                           self.route(["A","C"],-20)])
        self.assertEqual(len(results),2)
        self.assertEqual(results[0]["gross_base_units"],10)
        self.assertFalse(results[0]["actionable"])
        self.assertFalse(results[0]["atomic_simulation_verified"])
    def test_unquoted_and_malformed_excluded(self):
        bad=self.route(["A","B"],10)
        bad["status"]="UNQUOTABLE"
        self.assertEqual(shortlist([bad,{"status":"INDICATIVE_ONLY"}]),[])
    def test_bad_limit_rejected(self):
        with self.assertRaises(ValueError):shortlist([],0)
