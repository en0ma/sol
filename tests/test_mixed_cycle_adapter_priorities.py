import unittest
from arb.mixed_cycle_readiness import assess_mixed_routes

S="So11111111111111111111111111111111111111112"
U="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
R="4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"
def cycle(venues):
    tokens=[S,R,U,S]
    return {"all_pools_onchain_verified":True,"tokens":tokens,
            "legs":[{"venue":v,"pool":str(i),"from":tokens[i],"to":tokens[i+1]}
                    for i,v in enumerate(venues)]}

class AdapterPrioritiesTests(unittest.TestCase):
    def test_counts_missing_builder_types_not_simulated_liquidity(self):
        r=assess_mixed_routes({"cycles":[
            cycle(["orca","raydium_clmm","meteora_dlmm"]),
            cycle(["orca","raydium_clmm","meteora_dlmm"]),
            cycle(["orca","raydium_cpmm","meteora_dlmm"])]})
        self.assertEqual(r["missing_venue_counts"],{"meteora_dlmm":3,"raydium_clmm":2})
        self.assertEqual(r["verified_cross_venue_with_builder_types"],0)
        self.assertEqual(r["candidate_routes_by_fewest_missing_builders"][0]["missing_venue_count"],1)
        self.assertFalse(r["candidate_routes_by_fewest_missing_builders"][0]["actionable"])
        self.assertEqual(r["missing_venue_combinations"][0],
                         {"venues":["meteora_dlmm","raydium_clmm"],"count":2})
