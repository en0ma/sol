import unittest
from arb.opportunity_quote_pipeline import screen,shortlist
ROUTE={"start_mint":"A","legs":[{"venue":"orca","pool":"p1","input_mint":"A","output_mint":"B"},
{"venue":"raydium_cpmm","pool":"p2","input_mint":"B","output_mint":"A"}]}
def observed():
    return [dict(x,amount_in=a,amount_out=b,quote_source="onchain",observed_unix=997,
                 liquidity_input_units=100000,source_authenticated=True)
            for x,a,b in zip(ROUTE["legs"],[1000,500],[500,1100])]
COSTS={"network_fee":2,"priority_fee":2,"compute_cost":2,
       "slippage_buffer":20,"quote_uncertainty_buffer":10}
class Tests(unittest.TestCase):
 def test_research_only(self):
    r=screen(ROUTE,observed(),COSTS,now=1000)
    self.assertEqual(r["conservative_net_start_mint_units"],64)
    self.assertFalse(r["opportunity_confirmed"])
    self.assertFalse(r["actionable"])
 def test_identity_fail(self):
    q=observed();q[1]["pool"]="other"
    with self.assertRaises(ValueError):screen(ROUTE,q,COSTS,now=1000)
 def test_amount_mismatch(self):
    q=observed();q[1]["amount_in"]=400
    self.assertEqual(screen(ROUTE,q,COSTS,now=1000)["status"],"UNASSESSABLE")
 def test_missing_quotes_are_not_profits(self):
    r=shortlist([ROUTE],{},{},now=1000)
    self.assertEqual(r["assessable_routes"],0)
 def test_rank_does_not_claim_execution(self):
    r=shortlist([ROUTE],{0:observed()},{0:COSTS},now=1000)
    self.assertEqual(r["positive_declared_cost_candidates"],1)
    self.assertFalse(r["simulation_verified"])
if __name__=="__main__":unittest.main()
