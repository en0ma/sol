import unittest
from arb.signed_transaction_inventory import collect

class TransactionInventoryTests(unittest.TestCase):
    def inputs(self):
        return ({"routes":[{"index":3,"status":"AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE",
                             "venues":["orca","raydium_cpmm"],"fixture":"route-3.json"}]},
                {"status":"SIX_VENUE_SIGNED_OFFLINE_RESEARCH","broadcast":False,"actionable":False,
                 "signed_attempted":1,
                 "route_decisions":{"decisions":[{"index":3,"signed_execution_verified":True,
                   "observed_gross_delta_start_mint_base_units":123,
                   "observed_compute_units":250000,"net_profitability_verified":False,
                   "actionable":False,"broadcast":False}]}})
    def test_signed_gross_is_never_promoted_to_net(self):
        a,b=self.inputs()
        report=collect(a,b)
        self.assertEqual(report["signed_accepted"],1)
        self.assertEqual(report["rows"][0]["venues"],"orca>raydium_cpmm")
        self.assertEqual(report["rows"][0]["gross_delta_base_units"],123)
        self.assertIsNone(report["rows"][0]["net_delta_base_units"])
        self.assertEqual(report["rows"][0]["profitability"],"UNKNOWN_COSTS")
        self.assertEqual(report["confirmed_profitable"],0)
    def test_unattempted_source_candidates_remain_visible(self):
        a,b=self.inputs()
        a["routes"].append({"index":4,"status":"SOURCE_BLOCKED","venues":["orca","pumpswap"]})
        report=collect(a,b)
        self.assertEqual(report["signed_attempted"],1)
        self.assertEqual(report["source_routes"],2)
        self.assertEqual(report["rows"][1]["simulation_status"],"NOT_ATTEMPTED")
    def test_quote_blockers_explained(self):
        a,b=self.inputs()
        a["routes"].append({"index":4,"venues":["orca","pumpswap"]})
        ranking={"all_results":[{"index":3,"status":"GROSS_INDICATIVE_ONLY",
                                 "gross_delta_start_mint_base_units":123,"positive_gross":True},
                                {"index":4,"status":"QUOTE_BLOCKED",
                                 "reason":"effective fee not authenticated"}]}
        result=collect(a,b,ranking)
        self.assertEqual(result["rows"][1]["reason"],"effective fee not authenticated")
        ranking["all_results"][1]["index"]=3
        with self.assertRaises(ValueError):collect(a,b,ranking)
    def test_signed_negative_gross_not_promoted_to_net(self):
        a,b=self.inputs()
        b["route_decisions"]["decisions"][0]["observed_gross_delta_start_mint_base_units"]=-201
        result=collect(a,b)
        self.assertEqual(result["observed_gross_loss_count"],1)
        self.assertEqual(result["rows"][0]["profitability"],"GROSS_LOSS_NET_NOT_VERIFIED")
        self.assertEqual(result["confirmed_unprofitable"],0)
        self.assertIsNone(result["rows"][0]["net_delta_base_units"])
    def test_source_quote_sign_mismatch_rejected(self):
        a,b=self.inputs()
        ranking={"all_results":[{"index":3,"status":"GROSS_INDICATIVE_ONLY",
                                 "gross_delta_start_mint_base_units":-1,
                                 "positive_gross":True}]}
        with self.assertRaises(ValueError):collect(a,b,ranking)
    def test_rejection(self):
        a,b=self.inputs()
        b["route_decisions"]["decisions"][0]["signed_execution_verified"]=False
        self.assertEqual(collect(a,b)["rows"][0]["simulation_status"],"SIGNED_REJECTED")
    def test_duplicate_or_unknown_route_rejected(self):
        a,b=self.inputs()
        b["route_decisions"]["decisions"][0]["index"]=99
        with self.assertRaises(ValueError):collect(a,b)
    def test_forged_net_profit_rejected(self):
        a,b=self.inputs()
        b["route_decisions"]["decisions"][0]["net_profitability_verified"]=True
        with self.assertRaises(ValueError):collect(a,b)
    def test_unsafe_broadcast_rejected(self):
        a,b=self.inputs()
        b["broadcast"]=True
        with self.assertRaises(ValueError):collect(a,b)

if __name__=="__main__":unittest.main()
