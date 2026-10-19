import unittest
from unittest.mock import patch
from arb.orca_swap_v2_fixture_probe import classify, run

def fixture():
    return {
        "structurally_verified": True, "address": "pool", "slot": 27,
        "pool": {"tick_current_index": 10, "tick_spacing": 1,
                 "token_vault_a": "vault-a", "token_vault_b": "vault-b"},
        "mints": ["mint-a", "mint-b"],
        "mint_accounts": [{"owner": "token-a"}, {"owner": "token-b"}],
        "tick_arrays": [], "oracle_evidence": {"address": "oracle", "same_slot_verified": False},
        "extension_risk": {"requires_specialized_quote_support": True},
    }

class SwapV2FixtureProbeTests(unittest.TestCase):
    def test_missing_ticks_and_oracle_fail_closed(self):
        result = classify(fixture())
        self.assertIn("DIRECTIONAL_TICKS_INCOMPLETE", result["blockers"])
        self.assertIn("ORACLE_NOT_INITIALIZED_IN_SNAPSHOT", result["blockers"])
        self.assertIn("FEE_MODE_NOT_VERIFIED", result["blockers"])
        self.assertIn("OFFLINE_PROVISIONING_MINTS_DO_NOT_MATCH_POOL", result["blockers"])
        self.assertFalse(result["signed_simulation_verified"])
        self.assertFalse(result["executable_quote"])

    def test_invalid_snapshot_rejected(self):
        with self.assertRaises(ValueError):
            classify({"structurally_verified": False})

    def test_snapshot_error_yields_nonexecutable_report(self):
        with patch("arb.orca_swap_v2_fixture_probe.snapshot", side_effect=ValueError("stale")):
            result = run("http://127.0.0.1:8899")
        self.assertEqual(result["status"], "FIXTURE_NOT_VERIFIED")
        self.assertFalse(result["broadcast"])
        self.assertFalse(result["actionable"])

    def test_nonloopback_rejected(self):
        with self.assertRaises(ValueError):
            run("https://api.mainnet-beta.solana.com")
