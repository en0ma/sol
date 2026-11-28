import unittest
from arb.pumpswap_source_fee_envelope import directional_quote_scenarios,compare_directional_scenarios

class DirectionalFeeTests(unittest.TestCase):
    def scenarios(self,from_base,amount=10000):
        return directional_quote_scenarios(amount_in=amount,base_reserve=1000000,
            quote_reserve=2000000,quote_spendable=2000000,
            from_base=from_base,component_fee_bps=[20,5,5])
    def test_sell_fees_are_quote_denominated_in_hypothesis(self):
        rows=self.scenarios(True)
        self.assertEqual(len(rows),3)
        for r in rows:
            self.assertEqual(r["gross_quote_base_units"],2000000*10000//1010000)
            self.assertEqual(r["modeled_output_base_units"],r["gross_quote_base_units"]-r["fee_quote_base_units"])
            self.assertEqual(r["input_budget_unspent_base_units"],0)
    def test_buy_budget_inversion_conserves_input(self):
        for r in self.scenarios(False):
            self.assertEqual(r["net_quote_input_base_units"]+r["fee_quote_base_units"]+
                r["input_budget_unspent_base_units"],10000)
            self.assertEqual(r["modeled_output_base_units"],
                1000000*r["net_quote_input_base_units"]//(2000000+r["net_quote_input_base_units"]))
    def test_matching_scenario_never_promoted(self):
        rows=self.scenarios(True)
        out=rows[0]["modeled_output_base_units"]
        c=compare_directional_scenarios({"candidates":[{"tier":"test","directional_fee_scenarios":rows}]},out)
        self.assertGreaterEqual(c["matching_scenario_count"],1)
        self.assertFalse(c["effective_fee_verified"])
        self.assertFalse(c["protocol_exact_verified"])
        self.assertFalse(c["broadcast"])
        self.assertEqual(compare_directional_scenarios(None,out)["scenario_count"],0)
    def test_invalid_fee_rate_refused(self):
        with self.assertRaises(ValueError):
            directional_quote_scenarios(amount_in=100,base_reserve=1000,quote_reserve=2000,
                quote_spendable=1000,from_base=False,component_fee_bps=[10000,0,0])
if __name__=="__main__":unittest.main()
