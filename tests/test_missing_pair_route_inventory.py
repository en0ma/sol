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

    def test_authenticated_canonical_venue_reaches_missing_pair_inventory(self):
        """A verified unclassified Raydium owner becomes a builder-ready pair."""
        import base64
        from unittest.mock import patch
        from arb.token_cycle_verify import verify_graph, RAYDIUM_PROGRAM
        from arb.orca_whirlpool import USDC

        graph={"cycles":[{"tokens":[SOL,USDC,SOL],"legs":[
            {"venue":"raydium_unclassified","pool":"cpmm-pool",
             "from":SOL,"to":USDC},
            {"venue":"meteora_unclassified","pool":"dlmm-pool",
             "from":USDC,"to":SOL}]}]}
        from arb import meteora_dlmm
        def account_info(url,method,params):
            owner=(RAYDIUM_PROGRAM if params[0]=="cpmm-pool"
                   else meteora_dlmm.PROGRAM)
            return {"value":{"owner":owner,"executable":False,
                    "data":[base64.b64encode(b"pool").decode(),"base64"]}}
        with patch("arb.token_cycle_verify.call",side_effect=account_info), \
             patch("arb.token_cycle_verify.decode",
                   return_value={"token_0_mint":SOL,"token_1_mint":USDC}), \
             patch("arb.token_cycle_verify.verify_vaults",
                   return_value={"verified":True}), \
             patch("arb.token_cycle_verify.meteora_dlmm.decode",
                   return_value={"token_x_mint":SOL,"token_y_mint":USDC}), \
             patch("arb.token_cycle_verify.meteora_dlmm.verify"):
            verified=verify_graph("http://127.0.0.1:8899",graph)
        self.assertTrue(verified["cycles"][0]["all_pools_onchain_verified"])
        result=find_unverified_pairs(verified)
        self.assertEqual(result["pairings_with_verified_closed_route_candidates"],1)
        self.assertEqual(result["candidates"][0]["pair"],
                         ["meteora_dlmm","raydium_cpmm"])
        self.assertEqual(result["candidates"][0]["selected_route"]["legs"][0]
                         ["original_venue_hint"],"raydium_unclassified")
        self.assertFalse(result["candidates"][0]["atomic_signed_simulation_verified"])
        self.assertFalse(result["actionable"])
        self.assertFalse(result["broadcast"])
