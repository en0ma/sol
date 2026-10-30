"""Coordinator consumes admitted pool registry and existing 2-6-leg executor."""
import unittest
from unittest.mock import patch
from arb.atomic_graph_coordinator import coordinate_registered_cycle_offline, registered_cycles_for_coordinator, run_registered_cycle_batch_offline, rank_registered_cycle_candidates, coordinate_ranked_registered_cycles_offline, observed_registered_signed_cycle_economics

VENUES=("orca","raydium_cpmm","meteora_damm_v2","pumpswap","meteora_dlmm","raydium_clmm")

def case(n):
    tokens=[f"T{i}" for i in range(n)]+["T0"]
    legs=[{"venue":VENUES[i],"pool":f"P{i}",
           "input":tokens[i],"output":tokens[i+1]} for i in range(n)]
    reg={"pools":[{"venue":leg["venue"],"address":leg["pool"],
                   "mints":[leg["input"],leg["output"]]} for leg in legs]}
    st={(leg["venue"],leg["pool"]):{"verified_state":True} for leg in legs}
    ev={key:{"verified_account_evidence":True} for key in st}
    ac=[f"token-account-{i}" for i in range(n+1)]
    return reg,{"start_mint":"T0","legs":legs},st,ev,ac

def run(n,**changes):
    reg,route,states,evidence,accounts=case(n)
    return coordinate_registered_cycle_offline(
        "http://127.0.0.1:8899",
        changes.get("registry",reg),changes.get("route",route),
        changes.get("states",states),changes.get("evidence",evidence),
        "owner",changes.get("accounts",accounts),1000,"signer",
        negative_instructions=lambda i,a:i,
        observe=lambda *a:{"signed_offline_observed":True,"output_base_units":1234})

class CoordinatorRegistryTests(unittest.TestCase):
    @patch("arb.atomic_graph_coordinator.coordinate_registered_cycle_offline")
    def test_ranked_native_quotes_drive_signed_coordinator_in_gross_order(self,run_signed):
        registry,_,states,evidence,accounts=case(3)
        route_rows=registered_cycles_for_coordinator(registry,max_cycles=2)["routes"]
        prepared={}
        for row in route_rows:
            key=tuple((leg["venue"],leg["pool"],leg["input"],leg["output"])
                      for leg in row["legs"])
            prepared[key]={"states":states,"evidence":evidence,"owner":"owner",
                           "token_accounts":accounts,"signer":"signer",
                           "negative_instructions":lambda i,a:i}
        def priced(venue,pool,mint_in,mint_out,amount):
            increment=20 if mint_in=="T1" else 1
            return {"source_verified":True,"source_slot":200,
                    "output_base_units":amount+increment}
        run_signed.side_effect=[
            {"signed_receipt":{"status":"SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED"},
             "signed_atomic_simulation_verified":True},
            {"signed_receipt":{"status":"ROLLBACK_UNVERIFIED"},
             "signed_atomic_simulation_verified":False}]
        report=coordinate_ranked_registered_cycles_offline(
            "http://127.0.0.1:8899",registry,1000,priced,prepared,max_cycles=2)
        self.assertEqual(report["price_quoted_candidates"],2)
        self.assertEqual(report["signed_atomic_verified_routes"],1)
        self.assertEqual(report["ranked_attempts"][0]["status"],
                         "SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED")
        self.assertFalse(report["net_profitability_verified"])
        self.assertFalse(report["broadcast"])
        self.assertEqual(run_signed.call_count,2)

    def test_signed_spl_gross_calculated_from_receipt_not_quote(self):
        _,route,_,_,_=case(3)
        positive={"status":"SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED",
                  "signed_atomic_simulation_verified":True,
                  "signed_cpi_per_leg_verified":True,
                  "rollback_failure_case_verified":True,
                  "signed_packet_crypto_bound":True,
                  "initial_balances_base_units":[1000,0,0,0],
                  "positive_post_balances_base_units":[0,0,0,1080],
                  "planned_inputs":[1000,1100,1050],
                  "actionable":False,"live_execution_approved":False,"broadcast":False}
        result=observed_registered_signed_cycle_economics(route,positive)
        self.assertEqual(result["gross_start_mint_base_units"],80)
        self.assertEqual(result["break_even_total_cost_base_units"],80)
        self.assertIsNone(result["net_start_mint_base_units"])
        self.assertFalse(result["net_profitability_verified"])
        self.assertFalse(result["actionable"])
        for change in ({"signed_cpi_per_leg_verified":False},
                       {"rollback_failure_case_verified":False},
                       {"signed_packet_crypto_bound":False},
                       {"positive_post_balances_base_units":[0,1,0,1080]},
                       {"planned_inputs":[999,1100,1050]},
                       {"positive_post_balances_base_units":[0,0,0,True]},
                       {"actionable":True}):
            with self.subTest(change=change):
                self.assertIsNone(observed_registered_signed_cycle_economics(
                    route,{**positive,**change})["gross_start_mint_base_units"])

    @patch("arb.atomic_graph_coordinator.simulate_adaptive_n_leg_offline")
    def test_registered_coordinator_exposes_only_real_signed_spl_gross(self,sim):
        reg,route,states,evidence,accounts=case(3)
        sim.return_value={
            "status":"SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED",
            "signed_atomic_simulation_verified":True,
            "signed_cpi_per_leg_verified":True,
            "rollback_failure_case_verified":True,
            "signed_packet_crypto_bound":True,
            "initial_balances_base_units":[1000,0,0,0],
            "positive_post_balances_base_units":[0,0,0,1125],
            "planned_inputs":[1000,1050,1100],
            "actionable":False,"live_execution_approved":False,"broadcast":False}
        outcome=coordinate_registered_cycle_offline(
            "http://127.0.0.1:8899",reg,route,states,evidence,
            "owner",accounts,1000,"signer",
            negative_instructions=lambda instructions,amounts:instructions)
        economics=outcome["observed_signed_economics"]
        self.assertEqual(economics["gross_start_mint_base_units"],125)
        self.assertIsNone(economics["net_start_mint_base_units"])
        self.assertFalse(outcome["coordinator_live_eligible"])
        self.assertFalse(outcome["broadcast"])

    def test_signed_route_gross_loss_cannot_be_approved_by_fee_accounting(self):
        _,route,_,_,_=case(2)
        receipt={"status":"SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED",
                 "signed_atomic_simulation_verified":True,
                 "signed_cpi_per_leg_verified":True,
                 "rollback_failure_case_verified":True,
                 "signed_packet_crypto_bound":True,
                 "initial_balances_base_units":[500,0,0],
                 "positive_post_balances_base_units":[0,0,470],
                 "planned_inputs":[500,480],
                 "actionable":False,"live_execution_approved":False,"broadcast":False}
        outcome=observed_registered_signed_cycle_economics(route,receipt)
        self.assertEqual(outcome["gross_start_mint_base_units"],-30)
        self.assertEqual(outcome["break_even_total_cost_base_units"],0)
        self.assertIsNone(outcome["net_start_mint_base_units"])

    def test_native_quote_callback_propagates_exact_amounts_between_legs(self):
        registry,_,_,_,_=case(3)
        called=[]
        def native(venue,pool,a,b,amount):
            called.append((venue,pool,a,b,amount))
            return {"source_verified":True,"source_slot":225,
                    "output_base_units":amount+7}
        ranking=rank_registered_cycle_candidates(
            registry,1000,native,max_cycles=2)
        self.assertEqual(len(ranking["ranked"]),2)
        self.assertEqual(len(called),6)
        for row in ranking["ranked"]:
            self.assertEqual(row["final_amount_base_units"],1021)
            self.assertEqual(row["gross_delta_base_units"],21)
            self.assertEqual([x["input_base_units"] for x in row["quoted_legs"]],
                             [1000,1007,1014])
            self.assertFalse(row["signed_simulation_verified"])
        self.assertFalse(ranking["net_profitability_verified"])
        self.assertFalse(ranking["broadcast"])

    def test_native_quote_unverified_or_float_result_is_blocked(self):
        registry,_,_,_,_=case(2)
        for result in ({"output_base_units":1010,"source_slot":1},
                       {"output_base_units":1010.5,"source_slot":1,"source_verified":True},
                       1010):
            with self.subTest(result=result):
                report=rank_registered_cycle_candidates(
                    registry,1000,lambda *args:result,max_cycles=1)
                self.assertEqual(len(report["ranked"]),0)
                self.assertEqual(len(report["blocked"]),1)
                self.assertFalse(report["actionable"])

    @patch("arb.atomic_graph_coordinator.coordinate_registered_cycle_offline")
    def test_batch_uses_registered_graph_and_explicit_preparation(self,execute):
        registry,_,states,evidence,accounts=case(3)
        candidates=registered_cycles_for_coordinator(registry,max_cycles=2)["routes"]
        self.assertEqual(len(candidates),2)
        first=candidates[0]
        key=tuple((leg["venue"],leg["pool"],leg["input"],leg["output"])
                  for leg in first["legs"])
        prepared={key:{"states":states,"evidence":evidence,"owner":"owner",
                       "token_accounts":accounts,"initial_amount":1000,
                       "signer":"signer","negative_instructions":lambda i,a:i}}
        execute.return_value={"signed_receipt":{"status":"SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED"},
                              "signed_atomic_simulation_verified":True}
        result=run_registered_cycle_batch_offline(
            "http://127.0.0.1:8899",registry,prepared,max_cycles=2)
        self.assertEqual(result["candidate_count"],2)
        self.assertEqual(result["prepared_routes"],1)
        self.assertEqual(result["signed_atomic_verified_routes"],1)
        self.assertEqual(result["routes"][1]["status"],"NOT_PREPARED_FOR_SIGNED_EXECUTION")
        self.assertFalse(result["actionable"])
        self.assertEqual(execute.call_count,1)

    @patch("arb.atomic_graph_coordinator.coordinate_registered_cycle_offline")
    def test_batch_route_failure_does_not_promote_or_stop_other_routes(self,execute):
        registry,_,states,evidence,accounts=case(3)
        paths=registered_cycles_for_coordinator(registry,max_cycles=2)["routes"]
        config={"states":states,"evidence":evidence,"owner":"owner",
                "token_accounts":accounts,"initial_amount":1000,
                "signer":"signer","negative_instructions":lambda i,a:i}
        prepared={tuple((leg["venue"],leg["pool"],leg["input"],leg["output"])
                        for leg in path["legs"]):dict(config) for path in paths}
        execute.side_effect=[ValueError("signed CPI failed"),
            {"signed_receipt":{"status":"ROLLBACK_UNVERIFIED"},
             "signed_atomic_simulation_verified":False}]
        result=run_registered_cycle_batch_offline(
            "http://127.0.0.1:8899",registry,prepared,max_cycles=2)
        self.assertEqual(result["prepared_routes"],2)
        self.assertEqual(result["signed_atomic_verified_routes"],0)
        self.assertEqual(result["routes"][0]["status"],"SIGNED_COORDINATOR_ROUTE_REJECTED")
        self.assertEqual(result["routes"][1]["status"],"ROLLBACK_UNVERIFIED")
        self.assertFalse(result["broadcast"])

    def test_registered_graph_enumeration_reuses_existing_cycle_finder(self):
        registry,route,states,evidence,accounts=case(3)
        found=registered_cycles_for_coordinator(registry)
        self.assertGreater(found["candidate_count"],0)
        self.assertTrue(any(r["hops"]==3 for r in found["routes"]))
        self.assertFalse(found["actionable"])
        for path in found["routes"]:
            self.assertLessEqual(path["hops"],6)
            self.assertGreaterEqual(path["hops"],2)
            self.assertFalse(path["signed_simulation_verified"])
        scoped={"pools":registry["pools"]+[
            {"venue":"meteora_dbc","address":"exploratory","mints":["T0","T1"]}]}
        self.assertEqual(registered_cycles_for_coordinator(scoped)["routes"],found["routes"])

    def test_registered_graph_rejects_duplicate_admitted_pool(self):
        registry,_,_,_,_=case(3)
        registry["pools"].append(dict(registry["pools"][0]))
        with self.assertRaisesRegex(ValueError,"duplicate"):
            registered_cycles_for_coordinator(registry)

    @patch("arb.atomic_graph_coordinator.simulate_adaptive_n_leg_offline")
    def test_all_two_to_six_lengths_dispatch_existing_signed_coordinator(self,sim):
        sim.return_value={"signed_atomic_simulation_verified":True,
                          "status":"SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED"}
        for n in range(2,7):
            with self.subTest(n=n):
                result=run(n)
                self.assertEqual(result["route_legs"],n)
                self.assertFalse(result["coordinator_live_eligible"])
                self.assertFalse(result["broadcast"])
                self.assertTrue(result["signed_atomic_simulation_verified"])
                args=sim.call_args.args
                self.assertEqual(len(args[1]),n)
                self.assertEqual(len(args[2]),n+1)
    @patch("arb.atomic_graph_coordinator.simulate_adaptive_n_leg_offline")
    def test_signed_failure_remains_failure(self,sim):
        sim.return_value={"signed_atomic_simulation_verified":False,
                          "status":"ROLLBACK_UNVERIFIED"}
        self.assertFalse(run(3)["signed_atomic_simulation_verified"])
    @patch("arb.atomic_graph_coordinator.simulate_adaptive_n_leg_offline")
    def test_reject_invalid_route_before_any_swap_builder(self,sim):
        for kind in ("unregistered","mints","disconnected","repeated","account"):
            with self.subTest(kind=kind):
                reg,route,states,evidence,accounts=case(3)
                if kind=="unregistered":route["legs"][1]["pool"]="unknown"
                if kind=="mints":reg["pools"][1]["mints"]=["wrong","T2"]
                if kind=="disconnected":route["legs"][1]["input"]="wrong"
                if kind=="repeated":
                    route["legs"][1]["venue"]=route["legs"][0]["venue"]
                    route["legs"][1]["pool"]=route["legs"][0]["pool"]
                if kind=="account":accounts[2]=accounts[1]
                with self.assertRaises(ValueError):
                    coordinate_registered_cycle_offline(
                        "http://127.0.0.1:8899",reg,route,states,evidence,
                        "owner",accounts,1000,"signer",
                        negative_instructions=lambda i,a:i)
        sim.assert_not_called()
    def test_remote_broadcast_never_allowed(self):
        reg,route,states,evidence,accounts=case(2)
        with self.assertRaises(ValueError):
            coordinate_registered_cycle_offline(
                "https://api.mainnet-beta.solana.com",reg,route,states,
                evidence,"owner",accounts,1000,"signer",
                negative_instructions=lambda i,a:i)

if __name__=="__main__":
    unittest.main()
