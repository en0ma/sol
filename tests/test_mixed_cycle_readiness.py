import unittest
from arb.mixed_cycle_readiness import assess_mixed_routes

def cycle(venues,verified=True):
    tokens=["SOL","RAY","USDC","SOL"]
    return {"all_pools_onchain_verified":verified,"tokens":tokens,
            "legs":[{"venue":v,"pool":str(i),"from":tokens[i],"to":tokens[i+1]}
                    for i,v in enumerate(venues)]}

class MixedReadinessTests(unittest.TestCase):
    def test_supported_types_are_not_simulation_evidence(self):
        r=assess_mixed_routes({"cycles":[
            cycle(["orca","raydium_cpmm","orca"]),
            cycle(["orca","raydium_clmm","meteora_dlmm"]),
            cycle(["orca","raydium_cpmm","orca"],False)]})
        self.assertEqual(r["verified_cross_venue_cycles"],2)
        self.assertEqual(r["verified_cross_venue_with_builder_types"],2)
        self.assertEqual(r["verified_orca_cpmm_cycles"],1)
        self.assertEqual(r["routes"][1]["unsupported_venues"],[])
        self.assertFalse(r["routes"][0]["signed_atomic_simulation_verified"])
        self.assertFalse(r["actionable"])

    def test_orca_only_not_mixed(self):
        r=assess_mixed_routes({"cycles":[cycle(["orca","orca","orca"])]})
        self.assertEqual(r["verified_cross_venue_cycles"],0)
