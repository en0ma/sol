"""Coordinator consumes admitted pool registry and existing 2-6-leg executor."""
import unittest
from unittest.mock import patch
from arb.atomic_graph_coordinator import coordinate_registered_cycle_offline, registered_cycles_for_coordinator

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
