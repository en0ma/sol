"""Candidate-only signed audit must not contaminate the main inventory."""
import json
import tempfile
import unittest
from pathlib import Path
from arb.m5_isolated_recent_signed_probe import select_isolated_routes,signed_summary

def route(mint, pool, *, status="NOT_ATTEMPTED"):
    return {"start_mint":mint,"hops":3,
        "legs":[{"venue":"meteora_dlmm","pool":pool,"input":mint,
                 "output":"B"},
                {"venue":"orca","pool":"old-ab","input":"B",
                 "output":"C"},
                {"venue":"raydium_cpmm","pool":"old-ca","input":"C",
                 "output":mint}],
        "simulation_status":status}

class IsolatedRecentSignedTests(unittest.TestCase):
    def test_candidate_only_selection_preserves_control_graph(self):
        graph={"status":"SOURCE_AUTHENTICATED_ROUTE_DISCOVERY_ONLY",
               "routes":[route("PREVIOUS","new"),route("NOVEL","old"),
                         route("NOVEL","new"),route("NOVEL","new")]}
        candidate=[{"venue":"meteora_dlmm","address":"new",
                    "mints":["NOVEL","B"],"source_verified_only":True}]
        out=select_isolated_routes(graph,{"PREVIOUS"},candidate,maximum=3)
        self.assertEqual(len(out["routes"]),1)
        self.assertEqual(out["routes"][0]["start_mint"],"NOVEL")
        self.assertEqual(len(graph["routes"]),4)
        self.assertTrue(out["baseline_control_unchanged"])
        self.assertFalse(out["actionable"])

    def test_unverified_identity_cannot_be_selected(self):
        graph={"status":"SOURCE_AUTHENTICATED_ROUTE_DISCOVERY_ONLY",
               "routes":[route("NOVEL","new")]}
        with self.assertRaises(ValueError):
            select_isolated_routes(graph,[],[
                {"venue":"meteora_dlmm","address":"new",
                 "source_verified_only":False}])

    def test_signed_summary_requires_rollback_and_crypto_bound_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            def row(id,mint):
                return {"id":id,"mints":[mint],"source_status":"CAPTURED",
                    "atomic_build_status":"SIGNED_ATOMIC_PACKET_BUILT",
                    "simulation_status":"SIGNED_SIMULATION_AND_ROLLBACK_VERIFIED",
                    "signed_transaction_signature":"test-signature"}
            rows=[row("A","NEW"),row("B","BAD"),row("C","CONTROL")]
            (root/"three-hop-inventory.json").write_text(
                json.dumps({"routes":rows}))
            proof={"signed_packet_crypto_bound":True,
                "signed_transaction_signature":"test-signature",
                "signed_atomic_simulation_verified":True,
                "rollback_failure_case_verified":True}
            (root/"receipt-A.json").write_text(json.dumps(proof))
            (root/"receipt-B.json").write_text(json.dumps({
                **proof,"rollback_failure_case_verified":False}))
            (root/"receipt-C.json").write_text(json.dumps(proof))
            result=signed_summary(root,{"CONTROL"})
            self.assertEqual(result["signed_and_rollback_verified_routes"],2)
            self.assertEqual(result["additional_distinct_verified_start_mints"],1)
            self.assertEqual(result["additional_verified_start_mints"],["NEW"])
            self.assertTrue(result["excluded_from_primary_inventory"])
            self.assertFalse(result["broadcast"])

    def test_no_signed_receipt_means_no_new_mints(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"three-hop-inventory.json").write_text(json.dumps({
                "routes":[{"id":"A","mints":["NEW"],
                    "source_status":"CAPTURED",
                    "atomic_build_status":"SIGNED_ATOMIC_PACKET_BUILT",
                    "simulation_status":"SIGNED_SIMULATION_AND_ROLLBACK_VERIFIED",
                    "signed_transaction_signature":"signature"}]}))
            result=signed_summary(root,set())
            self.assertEqual(result["additional_distinct_verified_start_mints"],0)
            self.assertEqual(result["signed_and_rollback_verified_routes"],0)

if __name__=="__main__":
    unittest.main()
