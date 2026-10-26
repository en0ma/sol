import unittest
from unittest.mock import patch
from arb.m5_three_venue_observed_economics import evaluate
class FeeProvenanceTests(unittest.TestCase):
    @patch("arb.m5_three_venue_observed_economics.accept",return_value=True)
    def test_external_fee_only_scenario_not_source_attested(self,_):
        f={"route_mints":["So11111111111111111111111111111111111111112","B","C","So11111111111111111111111111111111111111112"]}
        r={"planned_inputs":[100,80,60],
           "initial_balances_base_units":[100,0,0,0],
           "positive_post_balances_base_units":[0,0,0,120]}
        scenario=evaluate(f,r,observed_fee_lamports=3)
        self.assertFalse(scenario["fee_source_verified"])
        self.assertEqual(scenario["status"],"COST_SCENARIO_WITH_UNVERIFIED_FEE_INPUT")
        self.assertEqual(scenario["net_delta_start_mint_base_units"],17)
        observation={"kind":"INDEPENDENT_OBSERVED_TRANSACTION_FEE",
            "source":"getTransaction","signature_or_message_hash":"evidence-id","lamports":3}
        observed=evaluate(f,r,fee_observation=observation)
        self.assertTrue(observed["fee_source_verified"])
        self.assertEqual(observed["net_delta_start_mint_base_units"],17)
        self.assertFalse(observed["profitability_verified"])
        conflict=evaluate(f,r,fee_observation=observation,observed_fee_lamports=8)
        self.assertEqual(conflict["reason"],"INDEPENDENT_FEE_OBSERVATION_CONFLICT")
    @patch("arb.m5_three_venue_observed_economics.accept",return_value=True)
    def test_unidentified_fee_attestation_rejected(self,_):
        r={"planned_inputs":[100,80,60],
           "initial_balances_base_units":[100,0,0,0],
           "positive_post_balances_base_units":[0,0,0,120]}
        x=evaluate({"route_mints":["A","B","C","A"]},r,
          fee_observation={"kind":"INDEPENDENT_OBSERVED_TRANSACTION_FEE","source":"unknown","lamports":1},
          start_mint_base_units_per_sol=1000000,conversion_authenticated=True)
        self.assertEqual(x["reason"],"INDEPENDENT_FEE_OBSERVATION_INVALID")
if __name__=="__main__":unittest.main()
