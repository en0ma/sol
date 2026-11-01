import unittest
from arb.native_math_kernel import exact_constant_product_quote
from arb.seven_venue_native_model_gate import VENUE_MODELS,model_requirements,quote_native
from arb.offline_atomic_economic_gate import (audit_complete_atomic_economics,
    screen_prospective_atomic_cost_budget)

class EconomicModelGateTests(unittest.TestCase):
    def test_native_constant_product_exact_integer_fees(self):
        result=exact_constant_product_quote(reserve_in=1000,reserve_out=1000,
                                             amount_in=100,fee_rate=2500)
        self.assertEqual(result["amount_out_base_units"],90)
        self.assertEqual(result["swap_fee_input_base_units"],1)
        self.assertFalse(result["net_profitability_verified"])
        with self.assertRaises(ValueError):
            exact_constant_product_quote(reserve_in=1000,reserve_out=1000,
                                         amount_in=1,fee_rate=900000)
    def test_all_seven_models_explicitly_fail_closed_without_native_inputs(self):
        self.assertEqual(len(VENUE_MODELS),7)
        for venue in VENUE_MODELS:
            observed=model_requirements(venue)
            self.assertFalse(observed["signed_parity_verified"])
            self.assertFalse(observed["net_profitability_verified"])
            if venue!="raydium_cpmm":
                with self.subTest(venue=venue),self.assertRaises(ValueError):
                    quote_native(venue,rpc="local",pool="p"*44,
                                 mint_in="a"*44,amount_in=100)
    def test_full_atomic_route_never_converts_unpaid_fee_to_profit(self):
        route={"legs":[{"pool":"a"},{"pool":"b"}]}
        signed={"signed_atomic_execution_verified":True,
                "independent_spl_poststate_verified":True,
                "rollback_control_verified":True,
                "offline_only":True,"broadcast":False,
                "gross_start_mint_base_units":100}
        quoted={"status":"COMPLETE_QUOTE_CHAIN_ARITHMETIC_ONLY",
                "legs":[{},{}],
                "native_quote_authenticity_established_here":False}
        r=audit_complete_atomic_economics(route,signed,quoted,
                                           {"quoted_fee_lamports":5000})
        self.assertIsNone(r["net_base_units"])
        self.assertFalse(r["net_profitability_verified"])
        self.assertFalse(r["broadcast"])
        signed["offline_only"]=False
        r=audit_complete_atomic_economics(route,signed,quoted,{})
        self.assertEqual(r["status"],"ATOMIC_SIGNED_EVIDENCE_INCOMPLETE")


    def test_complete_cost_budget_is_prospective_not_paid_fee(self):
        route={"start_mint":"So11111111111111111111111111111111111111112",
               "legs":[{"pool":"a"},{"pool":"b"}]}
        signed={"signed_atomic_execution_verified":True,
                "independent_spl_poststate_verified":True,
                "rollback_control_verified":True,
                "offline_only":True,"broadcast":False,
                "gross_start_mint_base_units":100}
        chain={"status":"COMPLETE_QUOTE_CHAIN_ARITHMETIC_ONLY",
               "legs":[{},{}],
               "native_quote_authenticity_established_here":False}
        types=("network_fee","priority_fee","compute_cost","rent",
               "borrow_cost","tip")
        costs={name:{"amount_start_mint_base_units":2,
                     "start_mint":route["start_mint"],
                     "observation_id":"source-"+name,
                     "actual_fee_paid_verified":False,
                     "broadcast":False} for name in types}
        report=screen_prospective_atomic_cost_budget(route,signed,chain,costs)
        self.assertEqual(report["prospective_total_cost_start_mint_base_units"],12)
        self.assertEqual(report["prospective_net_base_units"],88)
        self.assertIsNone(report["net_base_units"])
        self.assertFalse(report["net_profitability_verified"])
        self.assertFalse(report["costs_independently_proven_as_paid"])
        with self.assertRaises(ValueError):
            screen_prospective_atomic_cost_budget(route,signed,chain,
                {**costs,"network_fee":{**costs["network_fee"],
                                       "actual_fee_paid_verified":True}})
        with self.assertRaises(ValueError):
            screen_prospective_atomic_cost_budget(route,signed,chain,
                {**costs,"rent":{**costs["rent"],
                                 "start_mint":"another-mint"}})
        with self.assertRaises(ValueError):
            screen_prospective_atomic_cost_budget(route,signed,chain,
                {**costs,"tip":{**costs["tip"],
                               "amount_start_mint_base_units":True}})
        with self.assertRaises(ValueError):
            screen_prospective_atomic_cost_budget(route,signed,chain,
                {**costs,"tip":{**costs["tip"],
                               "amount_start_mint_base_units":2**64-1}})
        self.assertEqual(
            screen_prospective_atomic_cost_budget(
                route,{**signed,"rollback_control_verified":False},chain,costs
            )["cost_budget_status"],"UNASSESSABLE")

if __name__=="__main__":unittest.main()
