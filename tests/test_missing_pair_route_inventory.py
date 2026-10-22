import unittest
from arb.missing_pair_route_inventory import find_unverified_pairs
from arb.orca_whirlpool import SOL

T="intermediate"
def c(a,b,verified=True):
    return {"all_pools_onchain_verified":verified,
        "tokens":[SOL,T,SOL],"legs":[
            {"venue":a,"pool":"p1","from":SOL,"to":T},
            {"venue":b,"pool":"p2","from":T,"to":SOL}]}
class MissingPairInventoryTests(unittest.TestCase):
    def test_unproven_pair_selected_without_execution_claim(self):
        r=find_unverified_pairs({"cycles":[c("raydium_clmm","meteora_dlmm")]})
        self.assertEqual(r["pairings_with_verified_closed_route_candidates"],1)
        row=r["candidates"][0]
        self.assertEqual(row["pair"],["meteora_dlmm","raydium_clmm"])
        self.assertFalse(row["atomic_signed_simulation_verified"])
        self.assertFalse(r["broadcast"])
    def test_already_proven_pair_excluded(self):
        r=find_unverified_pairs({"cycles":[c("orca","meteora_dlmm")]})
        self.assertEqual(r["pairings_with_verified_closed_route_candidates"],0)
    def test_unverified_pool_cycle_not_admitted(self):
        r=find_unverified_pairs({"cycles":[c("raydium_clmm","meteora_dlmm",False)]})
        self.assertFalse(r["candidates"])
    def test_missing_cycles_rejected(self):
        with self.assertRaises(ValueError):
            find_unverified_pairs({})

    def test_longer_cycle_is_inventory_only_not_executable(self):
        tokens=[SOL,"token1","token2","token3",SOL]
        venues=["raydium_clmm","meteora_dlmm","raydium_clmm","meteora_dlmm"]
        cycle={"all_pools_onchain_verified":True,"tokens":tokens,
            "legs":[{"venue":v,"pool":"pool"+str(i),
                     "from":tokens[i],"to":tokens[i+1]}
                    for i,v in enumerate(venues)]}
        out=find_unverified_pairs({"cycles":[cycle]})
        self.assertEqual(out["pairings_with_verified_closed_route_candidates"],1)
        self.assertFalse(out["candidates"][0]["selected_route"]["current_assembler_hop_limit_satisfied"])
        self.assertEqual(out["graph_cycle_diagnostics"]["unevidenced_pair_routes"],1)
