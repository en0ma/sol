import unittest
from unittest.mock import patch
from arb.atomic_graph_coordinator import compile_route, signed_packet, simulation_decision
from arb.venue_swap_adapter import build_leg

class GraphCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.legs=[{"venue":"orca","pool":"pool1","input_mint":"SOL","output_mint":"USDC"},
                   {"venue":"raydium_cpmm","pool":"pool2","input_mint":"USDC","output_mint":"SOL"}]
        self.tokens=["SOL","USDC","SOL"]
        self.states={("orca","pool1"):{"real":True},("raydium_cpmm","pool2"):{"real":True}}
        self.evidence={k:{} for k in self.states}
    def test_graph_calls_existing_venue_adapters_in_sequence(self):
        with patch("arb.atomic_graph_coordinator.build_leg",side_effect=["instruction1","instruction2"]) as builder:
            result=compile_route(self.legs,self.tokens,self.states,self.evidence,"payer",
                                 {"SOL":"account_sol","USDC":"account_usdc"},
                                 [100000,100],[1,1])
        self.assertEqual(result,["instruction1","instruction2"])
        self.assertEqual(builder.call_count,2)
    def test_disconnected_graph_rejected(self):
        legs=[dict(x) for x in self.legs]
        legs[1]["input_mint"]="WRONG"
        with self.assertRaises(ValueError):
            compile_route(legs,self.tokens,self.states,self.evidence,"payer",
                          {"SOL":"a","USDC":"b"},[100,10],[1,1])
    def test_fail_closed_no_broadcast_even_with_profit(self):
        result=simulation_decision(simulation_verified=True,rollback_verified=True,
                                   net_profit_base_units=999999,live_execution_approved=True)
        self.assertFalse(result["broadcast"])
        self.assertFalse(result["actionable"])
    def test_pumpswap_builder_requires_real_account_authentication(self):
        state={"base_mint":"base","quote_mint":"quote"}
        with self.assertRaisesRegex(ValueError,"authentication missing"):
            build_leg("pumpswap","pool",state,{},"owner","src","dst",
                      "base","quote",100,1)
    def test_pumpswap_uses_existing_exact_input_builder(self):
        state={"base_mint":"base","quote_mint":"quote"}
        addresses={"pool":"pool","user":"owner","base_mint":"base","quote_mint":"quote",
                   "user_base_token_account":"dst","user_quote_token_account":"src"}
        with patch("arb.pumpswap_instruction.build_instruction",return_value="pump_ix") as b:
            ix=build_leg("pumpswap","pool",state,
                         {"account_addresses_authenticated":True,"account_addresses":addresses},
                         "owner","src","dst","quote","base",100,1)
        self.assertEqual(ix,"pump_ix")
        self.assertEqual(b.call_args.args[0],"buy_exact_quote_in")

if __name__=="__main__":
    unittest.main()
