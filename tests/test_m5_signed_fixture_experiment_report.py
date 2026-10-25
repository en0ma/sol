import unittest
from unittest.mock import patch
from arb.m5_signed_fixture_experiment_report import evaluate
from arb.source_snapshot_manifest import digest

def fixture():
    a={"x":{"owner":"x","data":["AA==","base64"]}}
    return {"accounts":a,"state_account_addresses":["x"],"state_account_count":1,
            "state_accounts_observed_slot":7,"state_account_manifest_sha256":digest(a,["x"],7),
            "first_venue":"raydium_cpmm","second_venue":"raydium_amm_v4",
            "first_pool":"p","second_pool":"q","route_mints":["A","B","A"]}

def receipt():
    return {"route_pool_addresses":["p","q"],"route_mints":["A","B","A"],
            "initial_balances_base_units":[100,0,0],
            "positive_post_balances_base_units":[0,0,110],
            "first_leg_intermediate_received_base_units":80}

class Tests(unittest.TestCase):
    def test_mismatched_route_refused_without_quote(self):
        r=receipt();r["route_pool_addresses"]=["other","q"]
        with patch("arb.m5_signed_fixture_experiment_report.quote_experiment") as mock:
            report=evaluate(fixture(),r,observed_unix=1)
        mock.assert_not_called()
        self.assertIn("SIGNED_ROUTE_IDENTITY_MISMATCH",report["reason_codes"])
        self.assertFalse(report["broadcast"])
    def test_real_receipt_remains_diagnostic_without_independent_proof(self):
        study={"quotes":[{"amount_in":100,"amount_out":80},{"amount_in":80,"amount_out":110}],
               "accuracy":{"first_leg_deviation_bps":0,"second_leg_deviation_bps":0,
                 "signed_atomic_evidence_status":"VERIFIED","provenance_status":"UNVERIFIED",
                 "reconciliation_status":"UNVERIFIED"},
               "observed_risk":None}
        with patch("arb.m5_signed_fixture_experiment_report.quote_experiment",return_value=study) as mock:
            report=evaluate(fixture(),receipt(),observed_unix=12)
        self.assertEqual(mock.call_args.kwargs["amount_in"],100)
        self.assertEqual(report["observed_legs"][1]["input"],80)
        self.assertEqual(report["status"],"DIAGNOSTIC_ONLY")
        self.assertIn("SOURCE_TO_EXECUTION_PROVENANCE_UNVERIFIED",report["reason_codes"])
        self.assertIsNone(report["net_after_costs"])
        self.assertFalse(report["actionable"])
    def test_unconsumed_signed_intermediate_explicit(self):
        r=receipt();r["positive_post_balances_base_units"]=[0,5,110]
        study={"quotes":[{"amount_in":100,"amount_out":80},{"amount_in":80,"amount_out":110}],
               "accuracy":{"first_leg_deviation_bps":0,"second_leg_deviation_bps":0,
                 "signed_atomic_evidence_status":"UNVERIFIED","provenance_status":"UNVERIFIED",
                 "reconciliation_status":"UNVERIFIED"},"observed_risk":None}
        with patch("arb.m5_signed_fixture_experiment_report.quote_experiment",return_value=study):
            report=evaluate(fixture(),r,observed_unix=12)
        self.assertIn("SIGNED_SECOND_LEG_INPUT_DIFFERS_FROM_QUOTE",report["reason_codes"])
        self.assertIn("OBSERVED_INTERMEDIATE_UNCONSUMED",report["reason_codes"])
        self.assertEqual(report["intermediate_amount_gap_base_units"],5)
    def test_quote_failure_preserves_observed_continuity_failure(self):
        r=receipt();r["positive_post_balances_base_units"]=[0,5,110]
        with patch("arb.m5_signed_fixture_experiment_report.quote_experiment",
                   side_effect=ValueError("CPMM source fee/reserves unavailable")):
            result=evaluate(fixture(),r,observed_unix=1)
        self.assertIn("OBSERVED_INTERMEDIATE_UNCONSUMED",result["reason_codes"])
        self.assertEqual(result["intermediate_amount_gap_base_units"],5)
        self.assertIn("CPMM_EFFECTIVE_FEE_OR_RESERVES_UNAVAILABLE",result["reason_codes"])
        self.assertEqual(result["quoted_legs"],[])
        self.assertFalse(result["live_execution_approved"])
    def test_observed_input_quote_probe_keeps_failed_leg_independent(self):
        def cpmm(*args, **kwargs):
            raise ValueError("CPMM creator fee not verified")
        def v4(*args, **kwargs):
            return {"quote":{"venue":"raydium_amm_v4","pool":"q",
                  "input_mint":"B","output_mint":"A","amount_in":80,
                  "amount_out":110,"snapshot_slot":7}}
        with patch("arb.m5_signed_fixture_experiment_report.quote_cpmm_only",side_effect=cpmm), \
             patch("arb.m5_signed_fixture_experiment_report.quote_from_fixture",side_effect=v4), \
             patch("arb.m5_signed_fixture_experiment_report.quote_experiment",
                   side_effect=ValueError("CPMM source fee/reserves unavailable")):
            result=evaluate(fixture(),receipt(),observed_unix=1)
        probes=result["observed_input_quote_probes"]
        self.assertEqual(probes[0]["status"],"UNVERIFIED")
        self.assertEqual(probes[1]["status"],"INDICATIVE_OBSERVED_INPUT_COMPARISON")
        self.assertEqual(probes[1]["signed_input"],80)
        self.assertEqual(probes[1]["deviation_bps"],0)
        self.assertFalse(result["actionable"])
    def test_invalid_manifest_blocks_quote(self):
        f=fixture();f["state_account_manifest_sha256"]="bad"
        with patch("arb.m5_signed_fixture_experiment_report.quote_experiment") as mock:
            report=evaluate(f,receipt(),observed_unix=1)
        mock.assert_not_called()
        self.assertTrue(report["reason_codes"][0].startswith("MANIFEST_INVALID"))
if __name__=="__main__": unittest.main()
