"""Independent route quote arithmetic contract and deliberate tamper tests."""
import copy
import unittest
from arb.six_venue_quote_continuity import audit_ranked_source_quote_continuity

def example():
    fixture={"route_venues":["orca","raydium_cpmm","pumpswap"],
             "route_mints":["A","B","C","A"],
             "route_pool_addresses":["p1","p2","p3"],
             "state_accounts_observed_slot":221}
    values=[1200,1100,1010]
    row={"index":0,"status":"GROSS_INDICATIVE_ONLY",
         "start_mint":"A","input_base_units":1000,
         "output_base_units":1010,"gross_delta_start_mint_base_units":10,
         "positive_gross":True,"net_profitability_confirmed":False,
         "actionable":False,"live_execution_approved":False,"broadcast":False,
         "quotes":[{"venue":venue,"pool":pool,"input_mint":a,"output_mint":b,
                    "amount_out":out,"source_slot":221}
                   for venue,pool,a,b,out in zip(
                       fixture["route_venues"],fixture["route_pool_addresses"],
                       fixture["route_mints"][:-1],fixture["route_mints"][1:],values)]}
    rank={"status":"GROSS_SOURCE_BOUND_RANKING_ONLY","ranked":[row],
          "actionable":False,"live_execution_approved":False,"broadcast":False}
    return rank,[fixture]

class QuoteContinuityTests(unittest.TestCase):
    def test_exact_quoted_triangle_research_only(self):
        ranking,fixtures=example()
        result=audit_ranked_source_quote_continuity(ranking,fixtures,1000)
        self.assertEqual(result["checked_routes"],1)
        self.assertEqual(result["routes"][0]["gross_start_mint_base_units"],10)
        self.assertFalse(result["routes"][0]["native_pricing_independently_audited"])
        self.assertEqual(result["coordinator_eligible_routes"],0)

    def test_empty_no_quotable_route_still_research_only(self):
        ranking,_=example()
        ranking["ranked"]=[]
        result=audit_ranked_source_quote_continuity(ranking,[],1000)
        self.assertEqual(result["checked_routes"],0)
        self.assertFalse(result["actionable"])

    def test_source_slot_pool_and_direction_tamper_rejected(self):
        for change in (
            {"source_slot":222},{"pool":"not-authenticated"},
            {"venue":"meteora_dbc"},{"input_mint":"wrong"},
            {"output_mint":"wrong"},{"amount_out":True},
            {"amount_out":2**64}):
            with self.subTest(change=change):
                ranking,fixtures=example()
                ranking["ranked"][0]["quotes"][1].update(change)
                with self.assertRaisesRegex(ValueError,"quoted leg"):
                    audit_ranked_source_quote_continuity(ranking,fixtures,1000)

    def test_gross_and_route_output_must_reconcile(self):
        for patch in ({"output_base_units":1100},
                      {"gross_delta_start_mint_base_units":100},
                      {"positive_gross":False}):
            with self.subTest(patch=patch):
                ranking,fixtures=example()
                ranking["ranked"][0].update(patch)
                with self.assertRaisesRegex(ValueError,"integer gross"):
                    audit_ranked_source_quote_continuity(ranking,fixtures,1000)

    def test_no_tradable_or_net_flag_ever_accepted(self):
        ranking,fixtures=example()
        for key in ("actionable","broadcast","live_execution_approved",
                    "net_profitability_confirmed"):
            with self.subTest(key=key):
                forged=copy.deepcopy(ranking)
                if key in forged["ranked"][0]:
                    forged["ranked"][0][key]=True
                with self.assertRaises(ValueError):
                    audit_ranked_source_quote_continuity(forged,fixtures,1000)

if __name__=="__main__":
    unittest.main()
