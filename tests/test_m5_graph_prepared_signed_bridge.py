"""Prepared graph-native route -> existing signed N-leg verifier contract."""
import unittest
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from arb.m5_four_to_six_signed_handoff import execute_prepared_offline

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
VENUES=["orca","raydium_cpmm","raydium_clmm","meteora_dlmm"]
MINTS=["A","B","C","D","A"]
POOLS=["p0","p1","p2","p3"]
SOURCE={"fixture_kind":"AUTHENTICATED_FOUR_TO_SIX_HOP_SOURCE_ROUTE",
        "state_accounts_observed_slot":44,"state_account_manifest_sha256":"d"*64,
        "route_venues":VENUES,"route_pool_addresses":POOLS,
        "route_mints":MINTS,**SAFE}
ROWS=[{"venue":VENUES[i],"address":POOLS[i],
       "mints":[MINTS[i],MINTS[i+1]]} for i in range(4)]
TRACE=[{"index":i,"venue":VENUES[i],"pool":POOLS[i],"source_slot":44,
        "input_base_units":100-i,"output_base_units":99-i} for i in range(4)]
QUOTE={"status":"SOURCE_BOUND_INDICATIVE_CHAIN_NOT_EXECUTION_VERIFIED",
       "hops":4,"indicative_all_legs":True,"quoted_legs":TRACE,
       "input_base_units":100,"output_base_units":96,
       "gross_delta_start_mint_base_units":-4,**SAFE}
PREP={"states":{},"evidence":{},"owner":"offline",
      "token_accounts":["a","b","c","d","e"],
      "signer":object(),"negative_instructions":lambda *x:None}
RECEIPT={"status":"SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED",
         "signed_packet_crypto_bound":True,"signed_cpi_per_leg_verified":True,
         "rollback_failure_case_verified":True,"signed_atomic_simulation_verified":True,
         **SAFE}

class PreparedNativeSignedBridge(unittest.TestCase):
    def setUp(self):
        self.offline=patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"1"})
        self.offline.start()
        self.addCleanup(self.offline.stop)
        self.hydration=patch("arb.hydrated_fork_state_audit.verify_hydrated_state",
            return_value={"status":"HYDRATED_FORK_ACCOUNT_BYTES_MATCH",
                          "accounts_checked":4,"captured_source_slot":44,**SAFE})
        self.hydrated=self.hydration.start()
        self.addCleanup(self.hydration.stop)
        self.independent=patch("arb.m5_four_to_six_source_signed_acceptance.assess",
            return_value={"status":"VERIFIED_SIGNED_FOUR_TO_SIX_HOP_ROLLBACK",
                          "signed_atomic_simulation_verified":True,**SAFE})
        self.auditor=self.independent.start()
        self.addCleanup(self.independent.stop)

    @patch("arb.m5_four_to_six_signed_handoff.extract_pool_states",return_value=ROWS)
    @patch("arb.m5_four_to_six_signed_handoff.verify")
    @patch("arb.atomic_graph_coordinator.coordinate_registered_cycle_offline")
    def test_calls_existing_signed_cpi_rollback_engine(self,coordinator,verify,extract):
        coordinator.return_value={"signed_receipt":RECEIPT,
                                  "signed_atomic_simulation_verified":True,**SAFE}
        report=execute_prepared_offline("http://127.0.0.1:8899",SOURCE,QUOTE,PREP)
        self.assertEqual(report["status"],"GRAPH_SOURCE_SIGNED_ATOMIC_OFFLINE_VERIFIED")
        self.assertFalse(report["net_profitability_verified"])
        self.assertFalse(report["broadcast"])
        coordinator.assert_called_once()
        args=coordinator.call_args.args
        self.assertEqual([v["pool"] for v in args[2]["legs"]],POOLS)
        self.assertEqual(args[7],100)

    @patch("arb.m5_four_to_six_signed_handoff.extract_pool_states",return_value=ROWS)
    @patch("arb.m5_four_to_six_signed_handoff.verify")
    @patch("arb.atomic_graph_coordinator.coordinate_registered_cycle_offline")
    def test_signed_flags_alone_without_crypto_is_unverified(self,coordinator,*unused):
        coordinator.return_value={"signed_receipt":{**RECEIPT,
                                     "signed_packet_crypto_bound":False},
                                  "signed_atomic_simulation_verified":True,**SAFE}
        report=execute_prepared_offline("http://127.0.0.1:8899",SOURCE,QUOTE,PREP)
        self.assertFalse(report["signed_atomic_simulation_verified"])
        self.assertEqual(report["status"],"GRAPH_SOURCE_SIGNED_ATOMIC_UNVERIFIED")

    @patch("arb.m5_four_to_six_signed_handoff.extract_pool_states",return_value=ROWS)
    @patch("arb.m5_four_to_six_signed_handoff.verify")
    @patch("arb.atomic_graph_coordinator.coordinate_registered_cycle_offline")
    def test_wrong_source_amount_never_calls_signer(self,coordinator,*unused):
        bad={**QUOTE,"quoted_legs":[dict(x) for x in TRACE]}
        bad["quoted_legs"][2]["input_base_units"]=1
        with self.assertRaises(ValueError):
            execute_prepared_offline("http://127.0.0.1:8899",SOURCE,bad,PREP)
        coordinator.assert_not_called()

    @patch("arb.m5_four_to_six_signed_handoff.execute_prepared_offline")
    def test_separate_offline_artifact_is_parseable_json(self,execute):
        from arb.m5_four_to_six_signed_handoff import run_captured_offline
        execute.return_value={"status":"GRAPH_SOURCE_SIGNED_ATOMIC_UNVERIFIED",**SAFE}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/"source.json").write_text(json.dumps(SOURCE))
            (root/"native.json").write_text(json.dumps(QUOTE))
            path=root/"signed.json"
            run_captured_offline("http://127.0.0.1:8899",
                root/"source.json",root/"native.json",PREP,path)
            self.assertEqual(json.loads(path.read_text()),execute.return_value)

    @patch("arb.m5_four_to_six_signed_handoff.extract_pool_states",return_value=ROWS)
    @patch("arb.m5_four_to_six_signed_handoff.verify")
    @patch("arb.atomic_graph_coordinator.coordinate_registered_cycle_offline")
    def test_forged_hydrated_account_match_cannot_reach_signer(self,coordinator,*unused):
        self.hydrated.return_value={"status":"UNVERIFIED","accounts_checked":4,
                                    "captured_source_slot":44,**SAFE}
        with self.assertRaises(ValueError):
            execute_prepared_offline("http://127.0.0.1:8899",SOURCE,QUOTE,PREP)
        coordinator.assert_not_called()

    @patch("arb.m5_four_to_six_signed_handoff.extract_pool_states",return_value=ROWS)
    @patch("arb.m5_four_to_six_signed_handoff.verify")
    @patch("arb.next_ten_signed_atomic_offline.run_four_to_six_venue")
    def test_automatic_existing_signer_and_receipt_written(self,runner,*unused):
        from arb.m5_four_to_six_signed_handoff import run_graph_selected_automatic_offline
        runner.return_value={**RECEIPT,
            "route_venues":VENUES,"route_pool_addresses":POOLS,
            "route_mints":MINTS,
            "state_account_manifest_sha256":"d"*64,
            "state_accounts_observed_slot":44,
            "hydrated_fork_state_readback":{"status":"HYDRATED_FORK_ACCOUNT_BYTES_MATCH"}}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/"source.json").write_text(json.dumps(SOURCE))
            (root/"quote.json").write_text(json.dumps(QUOTE))
            target=root/"result.json"
            result=run_graph_selected_automatic_offline("http://127.0.0.1:8899",
                root/"source.json",root/"quote.json",target)
            self.assertEqual(result["status"],"GRAPH_SELECTED_SIGNED_ATOMIC_ACCEPTED")
            self.assertEqual(json.loads(target.read_text())["status"],result["status"])
            runner.assert_called_once()
            self.assertEqual(runner.call_args.kwargs["amount_in"],100)

    @patch("arb.m5_four_to_six_signed_handoff.extract_pool_states",return_value=ROWS)
    @patch("arb.m5_four_to_six_signed_handoff.verify")
    @patch("arb.next_ten_signed_atomic_offline.run_four_to_six_venue")
    def test_automatic_flags_only_cannot_bypass_independent_audit(self,runner,*unused):
        from arb.m5_four_to_six_signed_handoff import run_graph_selected_automatic_offline
        runner.return_value={**RECEIPT, "route_venues":VENUES,
            "route_pool_addresses":POOLS,"route_mints":MINTS,
            "state_account_manifest_sha256":"d"*64,
            "state_accounts_observed_slot":44,
            "hydrated_fork_state_readback":{"status":"HYDRATED_FORK_ACCOUNT_BYTES_MATCH"}}
        self.auditor.return_value={"status":"SOURCE_FOUR_TO_SIX_SIGNED_ROLLBACK_UNVERIFIED",
                                   "signed_atomic_simulation_verified":False,**SAFE}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/"source.json").write_text(json.dumps(SOURCE))
            (root/"quote.json").write_text(json.dumps(QUOTE))
            report=run_graph_selected_automatic_offline("http://127.0.0.1:8899",
                root/"source.json",root/"quote.json",root/"result.json")
        self.assertEqual(report["status"],"GRAPH_SELECTED_SIGNED_ATOMIC_UNVERIFIED")
        self.assertFalse(report["signed_atomic_simulation_verified"])

    @patch("arb.m5_four_to_six_signed_handoff.extract_pool_states",return_value=ROWS)
    @patch("arb.m5_four_to_six_signed_handoff.verify")
    @patch("arb.next_ten_signed_atomic_offline.run_four_to_six_venue")
    def test_automatic_rejects_quote_tamper_before_runner(self,runner,*unused):
        from arb.m5_four_to_six_signed_handoff import run_graph_selected_automatic_offline
        bad={**QUOTE,"quoted_legs":[dict(x) for x in TRACE]}
        bad["quoted_legs"][1]["input_base_units"]=5
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/"source.json").write_text(json.dumps(SOURCE))
            (root/"quote.json").write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                run_graph_selected_automatic_offline("http://127.0.0.1:8899",
                    root/"source.json",root/"quote.json",root/"result.json")
        runner.assert_not_called()

    @patch("arb.m5_four_to_six_signed_handoff.extract_pool_states",return_value=ROWS)
    @patch("arb.m5_four_to_six_signed_handoff.verify")
    @patch("arb.next_ten_signed_atomic_offline.run_four_to_six_venue")
    def test_real_source_coverage_never_promotes_to_native_quote(self,runner,*unused):
        from arb.m5_four_to_six_signed_handoff import run_graph_selected_source_coverage_offline
        runner.return_value={**RECEIPT}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/"source.json").write_text(json.dumps(SOURCE))
            report=run_graph_selected_source_coverage_offline(
                "http://127.0.0.1:8899",root/"source.json",root/"report.json")
            self.assertEqual(report["status"],"GRAPH_SOURCE_COVERAGE_SIGNED_ATOMIC_VERIFIED")
            self.assertFalse(report["native_full_route_quote_verified"])
            self.assertFalse(report["native_priced_research_opportunity"])
            self.assertFalse(report["net_profitability_verified"])
            self.assertEqual(json.loads((root/"report.json").read_text()),report)
            runner.assert_called_once()

    @patch("arb.m5_four_to_six_signed_handoff.extract_pool_states",return_value=ROWS)
    @patch("arb.m5_four_to_six_signed_handoff.verify")
    @patch("arb.next_ten_signed_atomic_offline.run_four_to_six_venue")
    def test_coverage_persists_missing_builder_blocker_without_false_signed_attempt(self,runner,*unused):
        from arb.m5_four_to_six_signed_handoff import run_graph_selected_source_coverage_offline
        runner.side_effect=ValueError("authenticated venue builder unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/"source.json").write_text(json.dumps(SOURCE))
            report=run_graph_selected_source_coverage_offline(
                "http://127.0.0.1:8899",root/"source.json",root/"report.json")
            self.assertEqual(report["status"],"GRAPH_SOURCE_COVERAGE_SIGNED_BLOCKED")
            self.assertFalse(report["signed_attempted"])
            self.assertFalse(report["signed_atomic_simulation_verified"])
            self.assertFalse(report["native_full_route_quote_verified"])
            self.assertIn("authenticated venue builder unavailable",report["reason"])
            self.assertEqual(json.loads((root/"report.json").read_text()),report)

    @patch("arb.m5_four_to_six_signed_handoff.extract_pool_states",return_value=ROWS)
    @patch("arb.m5_four_to_six_signed_handoff.verify")
    @patch("arb.next_ten_signed_atomic_offline.run_four_to_six_venue")
    def test_coverage_rejects_failed_independent_audit(self,runner,*unused):
        from arb.m5_four_to_six_signed_handoff import run_graph_selected_source_coverage_offline
        runner.return_value={**RECEIPT}
        self.auditor.return_value={**SAFE,"status":"UNVERIFIED",
                                   "signed_atomic_simulation_verified":False}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/"source.json").write_text(json.dumps(SOURCE))
            report=run_graph_selected_source_coverage_offline(
                "http://127.0.0.1:8899",root/"source.json",root/"report.json")
            self.assertFalse(report["signed_atomic_simulation_verified"])
            self.assertEqual(report["status"],"GRAPH_SOURCE_COVERAGE_SIGNED_UNVERIFIED")

    def test_fork_isolation_gate_blocks_prepared_signer(self):
        with patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"0"}):
            with self.assertRaises(ValueError):
                execute_prepared_offline("http://127.0.0.1:8899",SOURCE,QUOTE,PREP)

    def test_remote_rpc_denied_before_any_source_or_signing(self):
        with self.assertRaises(ValueError):
            execute_prepared_offline("https://api.mainnet-beta.solana.com",SOURCE,QUOTE,PREP)

if __name__=="__main__":
    unittest.main()
