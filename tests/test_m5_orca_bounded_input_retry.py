"""Never count a reduced-input retry without a genuinely verified receipt."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from arb.m5_three_hop_atomic_inventory import (
    offline_simulate, orca_tick_array_input_retries,
)

ORCA_6038 = ("signed prefix simulation failed: "
             "{'InstructionError': [0, {'Custom': 6038}]}")
RAYDIUM_2505 = ("signed prefix simulation failed: "
                "{'InstructionError': [0, {'Custom': 2505}]}")


class BoundedOfflineOrcaInputTests(unittest.TestCase):
    def report(self, folder):
        root = Path(folder)
        (root / "source-00.json").write_text(json.dumps({"fixture_kind": "test"}))
        (root / "three-hop-inventory.json").write_text(json.dumps({
            "status": "SOURCE_THREE_HOP_INVENTORY",
            "routes": [{
                "id": "3H-01",
                "fixture": "source-00.json",
                "source_status": "CAPTURED",
                "venues": ["orca", "raydium_cpmm", "meteora_damm_v2"],
                "pools": ["p1", "p2", "p3"],
                "atomic_build_status": "NOT_ATTEMPTED",
                "simulation_status": "NOT_ATTEMPTED",
                "actionable": False,
                "live_execution_approved": False,
                "broadcast": False,
            }],
            "actionable": False,
            "live_execution_approved": False,
            "broadcast": False,
        }))
        return root

    def signed_receipt(self):
        return {
            "status": "SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED",
            "signed_packet_crypto_bound": True,
            "signed_transaction_signature": "test-cryptographic-evidence-placeholder",
            "signed_atomic_simulation_verified": True,
            "rollback_failure_case_verified": True,
            "positive_error": None,
        }

    def simulate_mocked_route(self, fail, receipt):
        with tempfile.TemporaryDirectory() as directory:
            root = self.report(directory)
            with patch.dict(os.environ, {
                "SURFPOOL_EXPLICITLY_OFFLINE": "1",
                "SURFPOOL_DATASOURCE_RPC_URL": "",
            }), patch("arb.pumpswap_local_simulation.local_rpc_only"), patch(
                "arb.dlmm_offline_clock.align_permissioned_dlmm_clock",
                return_value={"status": "ALIGNED"}), patch(
                "arb.next_ten_signed_atomic_offline.run_four_to_six_venue",
                side_effect=[ValueError(fail), receipt]) as simulator:
                result = offline_simulate("http://127.0.0.1:8899",
                                          root, amount=100000)
            return result, simulator.call_args_list

    def test_only_isolated_orca_6038_receives_smaller_candidates(self):
        self.assertEqual(
            orca_tick_array_input_retries(
                ValueError(ORCA_6038), ["orca", "raydium_cpmm"], 100000),
            [10000, 1000])
        self.assertEqual(
            orca_tick_array_input_retries(
                ValueError(RAYDIUM_2505), ["raydium_cpmm", "orca"], 100000),
            [])
        self.assertEqual(
            orca_tick_array_input_retries(
                ValueError(ORCA_6038), ["raydium_cpmm", "orca"], 100000),
            [])
        self.assertEqual(
            orca_tick_array_input_retries(
                ValueError("unauthenticated Orca tick array"),
                ["orca"], 100000),
            [])
        self.assertEqual(
            orca_tick_array_input_retries(
                ValueError(ORCA_6038), ["orca"], 1),
            [])

    def test_reduced_signed_receipt_is_auditable(self):
        result, calls = self.simulate_mocked_route(ORCA_6038, self.signed_receipt())
        row = result["routes"][0]
        self.assertEqual([c.kwargs["amount_in"] for c in calls], [100000, 10000])
        self.assertEqual(row["signed_exact_input_base_units"], 10000)
        self.assertEqual([x["amount_base_units"] for x in row["signed_exact_input_attempts"]],
                         [100000, 10000])
        self.assertIn("6038", row["signed_exact_input_attempts"][0]["diagnostic"])
        self.assertEqual(row["simulation_status"],
                         "SIGNED_SIMULATION_AND_ROLLBACK_VERIFIED")
        self.assertFalse(row["broadcast"])

    def test_unverified_retry_receipt_not_accepted(self):
        receipt = self.signed_receipt()
        receipt["rollback_failure_case_verified"] = False
        result, _ = self.simulate_mocked_route(ORCA_6038, receipt)
        self.assertEqual(result["simulations_verified"], 0)
        self.assertEqual(result["routes"][0]["simulation_status"],
                         "SIGNED_SIMULATION_NOT_VERIFIED")

    def test_zero_output_large_input_retry_is_venue_and_code_bound(self):
        from arb.m5_three_hop_atomic_inventory import zero_output_input_retries
        orca = ("signed prefix simulation failed: "
                "{'InstructionError': [0, {'Custom': 6036}]}")
        cpmm = ("signed prefix simulation failed: "
                "{'InstructionError': [0, {'Custom': 2505}]}; "
                "program_log_tail=['Left: 0','Right: 0']")
        self.assertEqual(zero_output_input_retries(
            ValueError(orca), ["orca"], 100000), [1000000, 10000000])
        self.assertEqual(zero_output_input_retries(
            ValueError(cpmm), ["raydium_cpmm"], 100000), [1000000, 10000000])
        self.assertEqual(zero_output_input_retries(
            ValueError(cpmm), ["orca"], 100000), [])
        self.assertEqual(zero_output_input_retries(
            ValueError(cpmm.replace("Left: 0", "Left: 1")),
            ["raydium_cpmm"], 100000), [])
        self.assertEqual(zero_output_input_retries(
            ValueError(ORCA_6038), ["orca"], 100000), [])
        self.assertEqual(zero_output_input_retries(
            ValueError(orca), ["orca"], 2**63), [])

    def test_recovered_zero_output_still_requires_signed_rollback(self):
        orca = ("signed prefix simulation failed: "
                "{'InstructionError': [0, {'Custom': 6036}]}")
        result,calls=self.simulate_mocked_route(orca,self.signed_receipt())
        self.assertEqual([c.kwargs["amount_in"] for c in calls],
                         [100000, 1000000])
        row=result["routes"][0]
        self.assertEqual(row["signed_exact_input_base_units"],1000000)
        self.assertEqual(row["simulation_status"],
                         "SIGNED_SIMULATION_AND_ROLLBACK_VERIFIED")
        self.assertFalse(row["broadcast"])
        result,_=self.simulate_mocked_route(
            orca,dict(self.signed_receipt(),rollback_failure_case_verified=False))
        self.assertEqual(result["simulations_verified"],0)

    def test_liquidity_cliff_diagnostic_never_upgrades_6038(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.report(directory)
            observed={"status":"SOURCE_AUTHENTICATED_FIRST_DOWNWARD_TICK_DEPLETES_LIQUIDITY",
                      "causes_6038_proven":False,"actionable":False,
                      "broadcast":False}
            with patch.dict(os.environ, {
                "SURFPOOL_EXPLICITLY_OFFLINE":"1",
                "SURFPOOL_DATASOURCE_RPC_URL":"",
            }), patch("arb.pumpswap_local_simulation.local_rpc_only"), patch(
                "arb.dlmm_offline_clock.align_permissioned_dlmm_clock",
                return_value={}), patch(
                "arb.next_ten_signed_atomic_offline.run_four_to_six_venue",
                side_effect=ValueError(ORCA_6038)) as sign, patch(
                "arb.whirlpool_ticks.authenticated_downward_liquidity_cliff",
                return_value=observed) as audit:
                result=offline_simulate(
                    "http://127.0.0.1:8899",root,amount=100000)
        row=result["routes"][0]
        self.assertEqual(sign.call_count,3)
        audit.assert_called_once()
        self.assertEqual(row["orca_source_liquidity_cliff"],observed)
        self.assertEqual(result["simulations_verified"],0)
        self.assertEqual(row["simulation_status"],
                         "NOT_ATTEMPTED_OR_ABORTED_DURING_PREPARATION")
        self.assertFalse(row["broadcast"])

    def test_other_venue_failure_does_not_trigger_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.report(directory)
            with patch.dict(os.environ, {"SURFPOOL_EXPLICITLY_OFFLINE": "1",
                                         "SURFPOOL_DATASOURCE_RPC_URL": ""}), patch(
                "arb.pumpswap_local_simulation.local_rpc_only"), patch(
                "arb.dlmm_offline_clock.align_permissioned_dlmm_clock",
                return_value={}), patch(
                "arb.next_ten_signed_atomic_offline.run_four_to_six_venue",
                side_effect=ValueError(RAYDIUM_2505)) as simulator:
                result = offline_simulate("http://127.0.0.1:8899",
                                          root, amount=100000)
        self.assertEqual(simulator.call_count, 1)
        self.assertEqual(result["simulations_verified"], 0)
        self.assertEqual(result["routes"][0]["simulation_status"],
                         "NOT_ATTEMPTED_OR_ABORTED_DURING_PREPARATION")


if __name__ == "__main__":
    unittest.main()
