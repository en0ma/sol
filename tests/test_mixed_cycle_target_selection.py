import unittest
from arb.mixed_cycle_readiness import assess_mixed_routes
from arb.orca_whirlpool import SOL,USDC

T="4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"
def cycle(start,venues,prefix):
    tokens=[start,T,start] if len(venues)==2 else [start,T,USDC,start]
    return {"all_pools_onchain_verified":True,"tokens":tokens,
            "legs":[{"venue":v,"pool":prefix+str(i),"from":tokens[i],"to":tokens[i+1]} for i,v in enumerate(venues)]}

class VerifiedAdapterTargetTests(unittest.TestCase):
    def test_sort_before_truncation_retains_best_target(self):
        worse=[cycle(USDC,["orca","raydium_clmm","meteora_dlmm"],"bad"+str(i)) for i in range(52)]
        good=cycle(SOL,["meteora_dlmm","orca"],"good")
        r=assess_mixed_routes({"cycles":[*worse,good]})
        self.assertEqual(r["prioritized_candidate_total"],0)
        self.assertFalse(r["prioritized_candidates_truncated"])
        self.assertEqual(r["first_dlmm_only_offline_target"]["legs"],good["legs"])
        self.assertFalse(r["first_dlmm_only_offline_target"]["actionable"])

    def test_no_target_without_verified_dlmm_only_cycle(self):
        r=assess_mixed_routes({"cycles":[cycle(SOL,["orca","raydium_clmm"],"clmm")]})
        self.assertIsNone(r["first_dlmm_only_offline_target"])
