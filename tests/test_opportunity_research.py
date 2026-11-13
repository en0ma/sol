import copy,unittest
from arb.opportunity_research import evaluate_cycle

NOW=100000
def sample():
    return {"start_mint":"mint-A","legs":[
        {"venue":"a","pool":"pool-a","input_mint":"mint-A","output_mint":"mint-B",
         "amount_in":1000,"amount_out":500,"quote_source":"source-a","observed_unix":NOW-3,
         "liquidity_input_units":100000,"source_authenticated":True},
        {"venue":"b","pool":"pool-b","input_mint":"mint-B","output_mint":"mint-A",
         "amount_in":500,"amount_out":1100,"quote_source":"source-b","observed_unix":NOW-4,
         "liquidity_input_units":100000,"source_authenticated":True}],
         "costs_start_mint_units":{"network_fee":5,"priority_fee":2,"compute_cost":3,
             "slippage_buffer":40,"quote_uncertainty_buffer":25}}
class TestOpportunityResearch(unittest.TestCase):
    def test_conservative_candidate_not_execution(self):
        r=evaluate_cycle(sample(),as_of_unix=NOW)
        self.assertEqual((r["gross_start_mint_units"],r["estimated_costs_start_mint_units"],
                          r["conservative_net_start_mint_units"]),(100,75,25))
        self.assertTrue(r["positive_after_declared_costs"])
        self.assertFalse(r["profitability_confirmed"])
        self.assertFalse(r["actionable"])
        self.assertFalse(r["broadcast"])
    def test_stale_or_unauthed_quote_unassessable(self):
        c=sample();c["legs"][0]["observed_unix"]=NOW-90
        self.assertEqual(evaluate_cycle(c,as_of_unix=NOW)["status"],"UNASSESSABLE")
        c=sample();c["legs"][1]["source_authenticated"]=False
        self.assertIsNone(evaluate_cycle(c,as_of_unix=NOW)["conservative_net_start_mint_units"])
    def test_no_token_unit_comparison_across_open_path(self):
        c=sample();c["legs"][1]["output_mint"]="mint-C"
        self.assertEqual(evaluate_cycle(c,as_of_unix=NOW)["status"],"UNASSESSABLE")
    def test_no_hidden_unpriced_costs(self):
        c=sample();del c["costs_start_mint_units"]["priority_fee"]
        self.assertIsNone(evaluate_cycle(c,as_of_unix=NOW)["conservative_net_start_mint_units"])
    def test_insufficient_depth_and_route_discontinuity(self):
        c=sample();c["legs"][0]["liquidity_input_units"]=100
        c["legs"][1]["amount_in"]=400
        r=evaluate_cycle(c,as_of_unix=NOW)
        self.assertEqual(r["status"],"UNASSESSABLE")
        self.assertTrue(any("discontinuity" in x for x in r["reason_codes"]))
    def test_negative_net_not_opportunity(self):
        c=sample();c["costs_start_mint_units"]["slippage_buffer"]=200
        r=evaluate_cycle(c,as_of_unix=NOW)
        self.assertLess(r["conservative_net_start_mint_units"],0)
        self.assertFalse(r["positive_after_declared_costs"])
if __name__=="__main__":unittest.main()
