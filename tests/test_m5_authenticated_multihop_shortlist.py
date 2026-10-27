import unittest
from arb.m5_authenticated_multihop_shortlist import shortlist

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
def route(hops,venues):
    mints=["A","B","C","D","E","F"][:hops]+["A"]
    legs=[{"input":mints[i],"output":mints[i+1],
           "venue":venues[i],"pool":"p"+str(i)} for i in range(hops)]
    return {"hops":hops,"start_mint":"A","legs":legs}
class AuthenticatedMultihopShortlistTests(unittest.TestCase):
    def test_longer_routes_and_venue_diversity_prioritized(self):
        routes=[route(2,["orca","raydium_cpmm"]),
                route(4,["orca","raydium_cpmm","raydium_clmm","pumpswap"]),
                route(4,["orca","raydium_cpmm","raydium_clmm","pumpswap"])]
        report=shortlist({"routes":routes,"cycle_inventory_truncated":True,**SAFE},maximum=2)
        self.assertEqual([r["source_graph_route_index"] for r in report["selected"]],[1,0])
        self.assertEqual(report["selected_by_hops"],{"2":1,"4":1})
        self.assertFalse(report["selected"][0]["source_quote_verified"])
        self.assertEqual(report["net_profitable_count"],0)
        self.assertFalse(report["broadcast"])
    def test_wrong_mint_or_unsafe_graph_rejected(self):
        broken=route(2,["orca","raydium_cpmm"])
        broken["legs"][1]["input"]="X"
        with self.assertRaises(ValueError):
            shortlist({"routes":[broken],**SAFE})
        with self.assertRaises(ValueError):
            shortlist({"routes":[],"broadcast":True,"actionable":False,
                       "live_execution_approved":False})
    def test_four_hop_graph_is_unquoted_without_real_leg_evidence(self):
        report=shortlist({"routes":[route(4,["orca","raydium_cpmm",
            "meteora_dlmm","pumpswap"])],"cycle_inventory_truncated":False,**SAFE})
        self.assertEqual(report["selected_by_hops"],{"4":1})
        self.assertEqual(report["native_quoted_count"],0)
        self.assertFalse(report["selected"][0]["signed_simulation_verified"])

    def test_rejects_foreign_graph_report_even_with_valid_looking_routes(self):
        with self.assertRaises(ValueError):
            shortlist({"status":"UNTRUSTED_API_ROUTES","routes":[
                route(4,["orca","raydium_cpmm","meteora_dlmm","pumpswap"])],**SAFE})

    def test_native_adapter_coverage_is_not_a_native_quote(self):
        rows=[route(4,["orca","raydium_cpmm","raydium_clmm","raydium_amm_v4"]),
              route(4,["orca","raydium_cpmm","meteora_dlmm","pumpswap"])]
        result=shortlist({"routes":rows,**SAFE},maximum=2)
        self.assertEqual(result["native_adapter_covered_source_cycles"],1)
        self.assertEqual(result["native_adapter_covered_selected"],1)
        self.assertTrue(result["selected"][0]["native_adapter_coverage_only"])
        self.assertFalse(result["selected"][0]["full_native_quote_observed"])
        self.assertEqual(result["native_quoted_count"],0)
        self.assertEqual(result["missing_auxiliary_venue_occurrences"],
                         {"meteora_dlmm":1,"pumpswap":1})

    def test_no_routes_yields_no_fabricated_candidates(self):
        result=shortlist({"routes":[],"cycle_inventory_truncated":False,**SAFE})
        self.assertEqual(result["selected"],[])
        self.assertEqual(result["native_quoted_count"],0)
if __name__=="__main__":unittest.main()
