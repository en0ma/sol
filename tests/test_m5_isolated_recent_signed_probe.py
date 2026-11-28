"""Candidate-only signed audit must not contaminate the main inventory."""
import json
import os
import textwrap
from unittest.mock import patch
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

    def test_source_prepare_writes_parseable_control_and_graph(self):
        from arb.m5_isolated_recent_signed_probe import source_prepare
        baseline=[
            {"venue":"orca","address":"old-ab","mints":["B","C"]},
            {"venue":"raydium_cpmm","address":"old-ca","mints":["C","NOVEL"]},
            {"venue":"orca","address":"control-ab","mints":["X","Y"]},
            {"venue":"orca","address":"control-bc","mints":["Y","Z"]},
            {"venue":"orca","address":"control-ca","mints":["Z","X"]},
        ]
        candidates=[{"venue":"meteora_dlmm","address":"new",
                     "mints":["NOVEL","B"],"source_verified_only":True}]
        graph={"status":"SOURCE_AUTHENTICATED_ROUTE_DISCOVERY_ONLY",
               "routes":[route("NOVEL","new")]}

        def capture(_rpc, selected, root):
            (root/"three-hop-inventory.json").write_text(json.dumps({
                "routes":selected["routes"],
                "source_captured_start_mints":["NOVEL"],
                "attempted_source_captures":1}))

        with tempfile.TemporaryDirectory() as d, \
             patch("arb.next_ten_fork_pool_probe.probe",return_value={}), \
             patch("arb.m5_three_hop_atomic_inventory.diversified_three_hop_graph",
                   return_value=graph), \
             patch("arb.m5_three_hop_atomic_inventory.source_capture",
                   side_effect=capture):
            report=source_prepare("http://127.0.0.1:8899",baseline,candidates,d)
            self.assertEqual(report["captured_routes"],1)
            root=Path(d)
            control=(root/"control-topology-starts.json").read_text()
            captured_graph=(root/"graph.json").read_text()
            self.assertEqual(json.loads(control),["X","Y","Z"])
            self.assertEqual(json.loads(captured_graph)["routes"],graph["routes"])
            self.assertTrue(control.endswith("\n"))
            self.assertTrue(captured_graph.endswith("\n"))

    def test_workflow_json_writers_and_recent_summary_round_trip(self):
        workflow=(Path(__file__).resolve().parents[1]/
                  ".github/workflows/m5-three-hop-atomic-inventory.yml").read_text()
        # YAML literal blocks preserve Python backslashes verbatim.
        self.assertNotIn(r"\\n",workflow)
        marker='root=Path(os.environ["RUNNER_TEMP"])/"source-artifact/triangles/isolated-recent"'
        lines=workflow.splitlines()
        start=next(i for i,line in enumerate(lines) if marker in line)
        end=next(i for i in range(start,len(lines)) if lines[i].strip()=="PY")
        script=textwrap.dedent("\n".join(lines[start-2:end]))
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"source-artifact/triangles/isolated-recent"
            root.mkdir(parents=True)
            summary=Path(d)/"step-summary.md"
            (root/"control-topology-starts.json").write_text(
                json.dumps(["CONTROL"])+"\n")
            (root/"three-hop-inventory.json").write_text(json.dumps({
                "routes":[{"id":"A","mints":["NEW"],
                    "source_status":"CAPTURED",
                    "atomic_build_status":"SIGNED_ATOMIC_PACKET_BUILT",
                    "simulation_status":"SIGNED_SIMULATION_AND_ROLLBACK_VERIFIED",
                    "signed_transaction_signature":"test-signature"}]}))
            (root/"receipt-A.json").write_text(json.dumps({
                "signed_packet_crypto_bound":True,
                "signed_transaction_signature":"test-signature",
                "signed_atomic_simulation_verified":True,
                "rollback_failure_case_verified":True}))
            with patch.dict(os.environ,{"RUNNER_TEMP":d,
                                        "GITHUB_STEP_SUMMARY":str(summary)}):
                exec(compile(script,"<workflow-report>","exec"),{})
            raw=(root/"isolated-recent-signed-summary.json").read_text()
            report=json.loads(raw)
            self.assertEqual(report["signed_and_rollback_verified_routes"],1)
            self.assertEqual(report["additional_verified_start_mints"],["NEW"])
            self.assertTrue(report["excluded_from_primary_inventory"])
            self.assertFalse(report["broadcast"])
            self.assertTrue(raw.endswith("\n"))
            self.assertTrue(summary.read_text().endswith("\n"))

if __name__=="__main__":
    unittest.main()
